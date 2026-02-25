"""Test cases for Zurich Instruments HDAWG."""
import enum
import json
import jsonschema
import logging
import unittest
from unittest.mock import call, Mock, ANY, PropertyMock
import warnings

import numpy as np
import numpy.testing as npt

import qmi.instruments.zurich_instruments.hdawg
from qmi.instruments.zurich_instruments import ZurichInstruments_Hdawg
from qmi.core.exceptions import QMI_InvalidOperationException, QMI_ApplicationException, QMI_TimeoutException, \
    QMI_RuntimeException
from tests.patcher import PatcherQmiContext as QMI_Context

_DEVICE_HOST = "localhost"
_DEVICE_PORT = 12345
_DEVICE_NAME = "DEV8888"
_schema_dict = {"vector": """{
  "$schema": "http://json-schema.org/draft-07/schema",
  "title": "AWG Command Table Schema",
  "version": "0.4",
  "description": "Schema for ZI HDAWG AWG Command Table",
  "definitions": {
    "header": {
      "properties": {
        "version": {
          "type": "string",
          "enum": [
            "0.4"
          ],
          "description": "File format version. This version must match with the relevant schema version."
        },
        "partial": {
          "description": "Set to true for incremental table updates",
          "type": "boolean",
          "default": "false"
        },
        "userString": {
          "description": "User-definable label",
          "type": "string",
          "maxLength": 30
        }
      },
      "required": [
        "version"
      ]
    },
    "table": {
      "items": {
        "$ref": "#/definitions/entry"
      },
      "minItems": 0,
      "maxItems": 1024
    },
    "entry": {
      "properties": {
        "index": {
          "$ref": "#/definitions/tableindex"
        },
        "waveform": {
          "$ref": "#/definitions/waveform"
        },
        "phase0": {
          "$ref": "#/definitions/phase"
        },
        "phase1": {
          "$ref": "#/definitions/phase"
        },
        "amplitude0": {
          "$ref": "#/definitions/amplitude"
        },
        "amplitude1": {
          "$ref": "#/definitions/amplitude"
        }
      },
      "additionalProperties": false
    },
    "tableindex": {
      "type": "integer",
      "minimum": 0,
      "maximum": 1023,
      "exclusiveMinimum": 0,
      "exclusiveMaximum": 1024
    },
    "waveform": {
      "properties": {
        "index": {
          "$ref": "#/definitions/waveformindex"
        },
        "length": {
          "$ref": "#/definitions/waveformlength"
        },
        "samplingRateDivider": {
          "$ref": "#/definitions/samplingratedivider"
        },
        "awgChannel0": {
          "$ref": "#/definitions/awgchannel"
        },
        "awgChannel1": {
          "$ref": "#/definitions/awgchannel"
        },
        "precompClear": {
          "$ref": "#/definitions/precompclear"
        },
        "playZero": {
          "$ref": "#/definitions/playzero"
        }
      },
      "additionalProperties": false,
      "oneOf": [
        {
          "required": [
            "index"
          ]
        },
        {
          "required": [
            "playZero",
            "length"
          ]
        }
      ]
    },
    "waveformindex": {
      "description": "Index of the waveform to play as defined with the assignWaveIndex sequencer instruction",
      "type": "integer",
      "minimum": 0,
      "maximum": 65535,
      "exclusiveMinimum": 0,
      "exclusiveMaximum": 0
    },
    "waveformlength": {
      "description": "The length of the waveform in samples",
      "type": "integer",
      "multipleOf": 16,
      "minimum": 32,
      "exclusiveMinimum": 0
    },
    "samplingratedivider": {
      "descpription": "Integer exponent n of the sampling rate divider: 2.4 GSa/s / 2^n, n in range 0 ... 13",
      "type": "integer",
      "minimum": 0,
      "maximum": 13
    },
    "awgchannel": {
      "description": "Assign the given AWG channel to signal output 0 &amp; 1",
      "type": "array",
      "minItems": 1,
      "maxItems": 2,
      "uniqueItems": true,
      "items": [
        {
          "type": "string",
          "enum": [
            "sigout0",
            "sigout1"
          ]
        }
      ]
    },
    "precompclear": {
      "description": "Set to true to clear the precompensation filters",
      "type": "boolean",
      "default": false
    },
    "playzero": {
      "description": "Play a zero-valued waveform for specified length of waveform, equivalent to the playZero sequencer instruction",
      "type": "boolean",
      "default": "false"
    },
    "phase": {
      "properties": {
        "value": {
          "description": "Phase value of the given sine generator in degree",
          "type": "number"
        },
        "increment": {
          "description": "Set to true for incremental phase value, or to false for absolute",
          "type": "boolean",
          "default": "false"
        }
      },
      "additionalProperties": false,
      "required": [
        "value"
      ]
    },
    "amplitude": {
      "properties": {
        "value": {
          "description": "Amplitude scaling factor of the given AWG channel",
          "type": "number",
          "minimum": -1.0,
          "maximum": 1.0,
          "exclusiveMinimum": 0,
          "exclusiveMaximum": 0
        },
        "increment": {
          "description": "Set to true for incremental amplitude value, or to false for absolute",
          "type": "boolean",
          "default": "false"
        }
      },
      "additionalProperties": false,
      "required": [
        "value"
      ]
    }
  },
  "properties": {
    "$schema": {
      "type": "string"
    },
    "header": {
      "$ref": "#/definitions/header"
    },
    "table": {
      "$ref": "#/definitions/table"
    }
  },
  "additionalProperties": false,
  "required": [
    "header"
  ]
}"""}
_SCHEMA = {"/DEV8888/awgs/0/commandtable/schema": [_schema_dict]}


class WaveformMock:
    def __init__(self):
        self.length = 0
        self.playZero = False

    def __dict__(self):
        return {"length": self.length, "playZero": self.playZero}

    def get_sequence_snippet(self):
        return "snippy-snip"


class ParameterMock:
    def __init__(self):
        self.waveform = WaveformMock()

    def __dict__(self):
        return {"waveform": self.waveform.__dict__()}


class ValidationError(Exception):
    pass


class CompilerStatusNotReady(enum.IntEnum):
    """Enumeration of compiler process status."""
    NOT_READY = 1
    READY_WITH_ERRORS = 0
    READY = -1


class UploadStatusReadyWithErrors(enum.IntEnum):
    """Enumeration of compiler process status."""
    WAITING = 2
    DONE = 1
    FAILED = 0
    BUSY = -1


class TestHDAWGInit(unittest.TestCase):
    """Testcase for HDAWG initialization."""

    def setUp(self):
        logging.getLogger("qmi.core.instrument").setLevel(logging.CRITICAL)

        self.ctx = QMI_Context("test_hdawg_openclose")
        self._awg_module = PropertyMock()
        self._awg_module.awg = Mock()
        self._awg_module.awg.raw_module = Mock()

    def tearDown(self):
        with warnings.catch_warnings():
            # Suppress warnings when instrument not correctly closed.
            warnings.simplefilter("ignore", ResourceWarning)

        logging.getLogger("qmi.core.instrument").setLevel(logging.NOTSET)

    def test_openclose(self):
        """Nominal open/close sequence."""

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst.toolkit.Session"
            ) as session_patch:
            self.hdawg = ZurichInstruments_Hdawg(
                self.ctx,
                "HDAWG",
                server_host=_DEVICE_HOST,
                server_port=_DEVICE_PORT,
                device_name=_DEVICE_NAME
            )
            self.hdawg.open()
            self.hdawg.close()

        expected_session_calls = [
            call(_DEVICE_HOST, _DEVICE_PORT),
            call().connect_device(_DEVICE_NAME),
            call().modules.awg.raw_module.set("device", _DEVICE_NAME),
            call().daq_server.setInt(f"/{_DEVICE_NAME}/system/awg/channelgrouping", 2),
            call().modules.awg.raw_module.set("index", 0),
            call().modules.awg.raw_module.execute(),
            call().modules.awg.raw_module.finished(),
            call().disconnect_device(_DEVICE_NAME),
        ]
        session_patch.assert_has_calls(expected_session_calls, any_order=True)

    def test_openclose_grouping_modes_0_1(self):
        """open/close sequence with 4x2 and 2x4 grouping modes."""

        for grouping in (0, 1):
            with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
                ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst.toolkit.Session"
            ) as session_patch:
                self.hdawg = ZurichInstruments_Hdawg(
                    self.ctx,
                    "HDAWG",
                    server_host=_DEVICE_HOST,
                    server_port=_DEVICE_PORT,
                    device_name=_DEVICE_NAME,
                    grouping=grouping
                )
                self.hdawg.open()
                self.hdawg.close()

            expected_session_calls = [
                call(_DEVICE_HOST, _DEVICE_PORT),
                call().connect_device(_DEVICE_NAME),
                call().modules.awg.raw_module.set("device", _DEVICE_NAME),
                call().daq_server.setInt(f"/{_DEVICE_NAME}/system/awg/channelgrouping", grouping),
                call().modules.awg.raw_module.set("index", 0),
                call().modules.awg.raw_module.execute(),
                call().modules.awg.raw_module.finished(),
                call().disconnect_device(_DEVICE_NAME),
            ]
            session_patch.assert_has_calls(expected_session_calls, any_order=True)

    def test_invalid_grouping_mode(self):
        """Test that trying to give an invalid grouping mode results in an error."""
        invalid_grouping_mode = 3
        expected_exception = f"Invalid grouping number: {invalid_grouping_mode}"

        with self.assertRaises(ValueError) as v_err:
            self.hdawg = ZurichInstruments_Hdawg(
                self.ctx,
                "HDAWG",
                server_host=_DEVICE_HOST,
                server_port=_DEVICE_PORT,
                device_name=_DEVICE_NAME,
                grouping=invalid_grouping_mode
            )

        self.assertEqual(expected_exception, str(v_err.exception))

    def test_failed_open1(self):
        """Failed open sequence due to self._awg_module being None."""
        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
        ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst.toolkit.Session"
        ) as session_patch:
            self._awg_module.awg.raw_module = None
            session_patch().modules = self._awg_module
            self.hdawg = ZurichInstruments_Hdawg(
                self.ctx,
                "HDAWG",
                server_host=_DEVICE_HOST,
                server_port=_DEVICE_PORT,
                device_name=_DEVICE_NAME
            )
            with self.assertRaises(AssertionError):
                self.hdawg.open()

        expected_session_calls = [
            call(_DEVICE_HOST, _DEVICE_PORT),
            call().connect_device(_DEVICE_NAME),
        ]
        session_patch.assert_has_calls(expected_session_calls)

    def test_failed_open2(self):
        """Failed open sequence due to self._daq_server being None."""
        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
        ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst.toolkit.Session"
        ) as session_patch:
            session_patch().daq_server = None
            self.hdawg = ZurichInstruments_Hdawg(
                self.ctx,
                "HDAWG",
                server_host=_DEVICE_HOST,
                server_port=_DEVICE_PORT,
                device_name=_DEVICE_NAME
            )
            with self.assertRaises(AssertionError):
                self.hdawg.open()

        expected_session_calls = [
            call(_DEVICE_HOST, _DEVICE_PORT),
            call().connect_device(_DEVICE_NAME),
        ]
        session_patch.assert_has_calls(expected_session_calls)

    def test_close_awg_module_not_finished(self):
        """Test close sequence such that the self.awg_module is not finished and finish() call has to be made."""
        self._awg_module.awg.raw_module.finished = Mock(side_effect=[False, True])

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst.toolkit.Session"
            ) as session_patch:
            session_patch().modules = self._awg_module
            self.hdawg = ZurichInstruments_Hdawg(
                self.ctx,
                "HDAWG",
                server_host=_DEVICE_HOST,
                server_port=_DEVICE_PORT,
                device_name=_DEVICE_NAME
            )
            self.hdawg.open()
            self.hdawg.close()

        expected_session_calls = [
            call(_DEVICE_HOST, _DEVICE_PORT),
            call().connect_device(_DEVICE_NAME),
            call().modules.awg.raw_module.set("device", _DEVICE_NAME),
            call().daq_server.setInt(f"/{_DEVICE_NAME}/system/awg/channelgrouping", 2),
            call().modules.awg.raw_module.set("index", 0),
            call().modules.awg.raw_module.execute(),
            call().modules.awg.raw_module.finished(),
            call().modules.awg.raw_module.finish(),
            call().modules.awg.raw_module.finished(),
            call().disconnect_device(_DEVICE_NAME),
        ]
        session_patch.assert_has_calls(expected_session_calls, any_order=True)

    def test_close_assertion_error(self):
        """Failed close sequence due to assertion error AWG module 'finished'."""
        self._awg_module.awg.raw_module.finished = Mock(return_value=False)

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst.toolkit.Session"
            ) as session_patch:
            session_patch().modules = self._awg_module
            self.hdawg = ZurichInstruments_Hdawg(
                self.ctx,
                "HDAWG",
                server_host=_DEVICE_HOST,
                server_port=_DEVICE_PORT,
                device_name=_DEVICE_NAME
            )
            self.hdawg.open()
            with self.assertRaises(AssertionError):
                self.hdawg.close()

        expected_session_calls = [
            call(_DEVICE_HOST, _DEVICE_PORT),
            call().connect_device(_DEVICE_NAME),
            call().modules.awg.raw_module.set("device", _DEVICE_NAME),
            call().daq_server.setInt(f"/{_DEVICE_NAME}/system/awg/channelgrouping", 2),
            call().modules.awg.raw_module.set("index", 0),
            call().modules.awg.raw_module.execute(),
            call().modules.awg.raw_module.finished(),
            call().modules.awg.raw_module.finish(),
            call().modules.awg.raw_module.finished(),
        ]
        session_patch.assert_has_calls(expected_session_calls, any_order=True)

    def test_failed_open_notclosed(self):
        """Open device that is already open."""
        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst.toolkit.Session"
            ):
            self.hdawg = ZurichInstruments_Hdawg(
                self.ctx,
                "HDAWG",
                server_host=_DEVICE_HOST,
                server_port=_DEVICE_PORT,
                device_name=_DEVICE_NAME
            )
            self.hdawg.open()
            with self.assertRaises(QMI_InvalidOperationException):
                self.hdawg.open()

            self.hdawg.close()

    def test_failed_close_notopen(self):
        """Close device that is not open."""
        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst.toolkit.Session"
            ):
            self.hdawg = ZurichInstruments_Hdawg(
                self.ctx,
                "HDAWG",
                server_host=_DEVICE_HOST,
                server_port=_DEVICE_PORT,
                device_name=_DEVICE_NAME
            )
            with self.assertRaises(QMI_InvalidOperationException):
                self.hdawg.close()


class TestHDAWG(unittest.TestCase):
    """Testcase for HDAWG functions."""

    def setUp(self):

        class CommandTableMock:
            table = [ParameterMock() for _ in range(1024)]
            self._table = table

            @staticmethod
            def as_dict():
                return {f"index {k}": v.__dict__() for k, v in enumerate(self._table)}

        logging.getLogger("qmi.instruments.zurich_instruments.hdawg").setLevel(logging.CRITICAL)

        ctx = QMI_Context("TestHDAWGMethods")
        self._awg_module = PropertyMock()
        self._awg_module.awg = Mock()
        self._awg_module.awg.raw_module = Mock()

        self._daq_server = PropertyMock()
        self._daq_server.get = Mock(return_value=_SCHEMA)

        self._device = PropertyMock()

        self.CommandTableMock = CommandTableMock

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst.toolkit.Session"
            ) as self.session_patch:
            self.session_patch().modules = self._awg_module
            self.session_patch().daq_server = self._daq_server
            self.session_patch().connect_device = Mock(return_value=self._device)
            self.hdawg = ZurichInstruments_Hdawg(
                ctx,
                "HDAWG",
                server_host=_DEVICE_HOST,
                server_port=_DEVICE_PORT,
                device_name=_DEVICE_NAME
            )
            self.hdawg.open()

    def tearDown(self):
        self._daq_server.reset_mock()
        self.hdawg.close()
        logging.getLogger("qmi.instruments.zurich_instruments.hdawg").setLevel(logging.NOTSET)

    def _check_get_value_string(self, node_path):
        expected_calls = [
            call.getString(f"/{_DEVICE_NAME}/{node_path}")
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def _check_get_value_int(self, node_path):
        expected_calls = [
            call.getInt(f"/{_DEVICE_NAME}/{node_path}")
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def _check_get_value_float(self, node_path):
        expected_calls = [
            call.getDouble(f"/{_DEVICE_NAME}/{node_path}")
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def _check_set_value(self, node_path, value):
        expected_calls = [
            call.set(f"/{_DEVICE_NAME}/{node_path}", value)
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def _check_set_value_int(self, node_path, value):
        expected_calls = [
            call.setInt(f"/{_DEVICE_NAME}/{node_path}", value)
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def _check_get_value_double(self, node_path):
        expected_calls = [
            call.getDouble(f"/{_DEVICE_NAME}/{node_path}")
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def _check_set_value_double(self, node_path, value):
        expected_calls = [
            call.setDouble(f"/{_DEVICE_NAME}/{node_path}", value)
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def test_generic_set(self):
        """Test setter."""
        node = "my/test/node"
        value = "value"
        self.hdawg.set_node_value(node, value)
        self._check_set_value(node, value)

        channel = 3
        node_mock = self.hdawg.awg_channel_map[channel]

        self.hdawg.set_node_value(node, value, channel)

        node_mock.root.connection.set.assert_called_once_with(f"/{_DEVICE_NAME}/{node}", value)

    def test_generic_get_string(self):
        """Test getter."""
        node = "my/test/node"
        value = "value"
        self._daq_server.getString.return_value = value
        result = self.hdawg.get_node_string(node)
        self._check_get_value_string(node)
        self.assertEqual(result, value)

        channel = 0
        node_mock = self.hdawg.awg_channel_map[channel]

        self.hdawg.get_node_string(node, channel)

        node_mock.root.connection.getString.assert_called_once_with(f"/{_DEVICE_NAME}/{node}")

    def test_generic_get_int(self):
        """Test getter."""
        node = "my/test/node"
        value = 123
        self._daq_server.getInt.return_value = value
        result = self.hdawg.get_node_int(node)
        self._check_get_value_int(node)
        self.assertEqual(result, value)

        channel = 2
        node_mock = self.hdawg.awg_channel_map[channel]

        self.hdawg.get_node_int(node, channel)

        node_mock.root.connection.getInt.assert_called_once_with(f"/{_DEVICE_NAME}/{node}")

    def test_generic_set_int(self):
        """Test setter."""
        node = "my/test/node"
        value = 123
        self.hdawg.set_node_int(node, value)
        self._check_set_value_int(node, value)

        channel = 5
        node_mock = self.hdawg.awg_channel_map[channel]

        self.hdawg.set_node_int(node, value, channel)

        node_mock.root.connection.set.assert_called_once_with(f"/{_DEVICE_NAME}/{node}", value)

    def test_generic_get_double(self):
        """Test getter."""
        node = "my/test/node"
        value = 123.456
        self._daq_server.getDouble.return_value = value
        result = self.hdawg.get_node_double(node)
        self._check_get_value_double(node)
        self.assertEqual(result, value)

        channel = 4
        node_mock = self.hdawg.awg_channel_map[channel]

        self.hdawg.get_node_double(node, channel)

        node_mock.root.connection.getDouble.assert_called_once_with(f"/{_DEVICE_NAME}/{node}")

    def test_generic_set_double(self):
        """Test setter."""
        node = "my/test/node"
        value = 123.345
        self.hdawg.set_node_double(node, value)
        self._check_set_value_double(node, value)

        channel = 7
        node_mock = self.hdawg.awg_channel_map[channel]

        self.hdawg.set_node_double(node, value, channel)

        node_mock.root.connection.set.assert_called_once_with(f"/{_DEVICE_NAME}/{node}", value)

    def test_get_idn(self):
        """Test get_idn."""
        vendor = "Zurich Instruments"
        model = "h-dog"
        serial = "1234"
        version = 3
        version_info = {"zi": {"about": {"version": {"value": [version, 2, 1]}}}}
        self._daq_server.get = Mock(return_value=version_info)
        self._daq_server.getString = Mock(side_effect=[model, serial])

        idn = self.hdawg.get_idn()

        self.assertEqual(vendor, idn.vendor)
        self.assertEqual(model, idn.model)
        self.assertEqual(serial, idn.serial)
        self.assertEqual(version, idn.version)

    def test_compile_and_upload(self):
        """Test compile sequence."""
        source = """
        wave w = "$FILE";
        var n = 0.0;
        for(i = 0; i < $COUNT; i++) {
            n += $INCR;
        }
        """
        replacements = {
            "$FILE": "w_a",
            "$COUNT": 100,
            "$INCR": 3.14
        }
        expected_source = """
        wave w = "w_a";
        var n = 0.0;
        for(i = 0; i < 100; i++) {
            n += 3.14;
        }
        """

        self._awg_module.awg.raw_module.getInt = Mock(side_effect=[0, 0, 0])  # compiler status; get index; elf status
        self._awg_module.awg.raw_module.getDouble = Mock(side_effect=[1.0])  # upload progress

        expected_calls = [
            call().modules.awg.raw_module.set("compiler/upload", 1),
            call().modules.awg.raw_module.set("compiler/sourcestring", expected_source),
            call().modules.awg.raw_module.getInt("compiler/status"),
            call().modules.awg.raw_module.getInt("elf/status"),
        ]

        self.hdawg.compile_and_upload(source, replacements)
        # Assert
        self.session_patch.assert_has_calls(expected_calls, any_order=True)
        self.assertTrue(self.hdawg.compilation_successful())

    def test_compile_empty_fails(self):
        """Test that empty programs are not accepted."""
        with self.assertRaises(QMI_ApplicationException):
            self.hdawg.compile_and_upload("")

        with self.assertRaises(QMI_ApplicationException):
            self.hdawg.compile_and_upload("// Hello")

        with self.assertRaises(QMI_ApplicationException):
            self.hdawg.compile_and_upload("/* Hello */")

        with self.assertRaises(QMI_ApplicationException):
            self.hdawg.compile_and_upload("""
                // Hello

                /* Hello */
                """)

    def test_valid_replacements(self):
        """Test replacement patterns"""
        cases = [
            ("par = $PAR;", {"$PAR": "value"}, "par = value;"),  # standard replace
            ("PAR = $PAR;", {"$PAR": "value"}, "PAR = value;"),  # $ distinguishes replacement from sequencer code
            ("par = $A;", {"$A": 1}, "par = 1;"),  # upper case parameter name
            ("par = $a;", {"$a": 3.14}, "par = 3.14;"),  # lower case parameter name
            ("par = $PAR1;", {"$PAR1": "value"}, "par = value;"),  # numbers in parameter name
            ("par = $A1;", {"$A1": 2}, "par = 2;"),
            ("par = $a1;", {"$a1": 3.14}, "par = 3.14;"),
            ("par = $PAR_;", {"$PAR_": "value"}, "par = value;"),  # underscore in parameter name
            ("par = $A_;", {"$A_": 3}, "par = 3;"),
            ("par = $a_;", {"$a_": 3.14}, "par = 3.14;"),
            ("par = $PAR$PAR", {"$PAR": "value"}, "par = valuevalue"),  # multiple replacements
            ("par = $PARAMETER + $PAR", {"$PARAMETER": 1, "$PAR": "value"}, "par = 1 + value"),  # test word boundaries
            ("par = $PARAMETER + $PAR", {"$PAR": 1, "$PARAMETER": "value"}, "par = value + 1"),
            ("par = $PAR + $PARAMETER + $PAR", {"$PAR": 1, "$PARAMETER": "value"}, "par = 1 + value + 1")
        ]

        for source, replacements, expected_source in cases:
            with self.subTest(source=source):
                self._awg_module.awg.raw_module.getInt.side_effect = [0, 0, 0]  # successful compilation; get index; upload completed
                self._awg_module.awg.raw_module.getDouble.side_effect = [1.0]  # upload progress

                self.hdawg.compile_and_upload(source, replacements)

                expected_calls = [
                    call("compiler/upload", 1),
                    call("compiler/sourcestring", expected_source)
                ]
                self._awg_module.awg.raw_module.set.assert_has_calls(expected_calls)
                self.assertTrue(self.hdawg.compilation_successful())
                self._awg_module.awg.raw_module.set.reset_mock()

    def test_invalid_replacements(self):
        """Test replacement patterns."""
        with self.assertRaises(NameError):
            self.hdawg.compile_and_upload("", {"$1": 0})

        with self.assertRaises(NameError):
            self.hdawg.compile_and_upload("", {"$_": 0})

        with self.assertRaises(NameError):
            self.hdawg.compile_and_upload("", {"$_1": 0})

    def test_incomplete_replacements(self):
        """Test replacement patterns."""
        with self.assertRaises(KeyError):
            self.hdawg.compile_and_upload("$PAR1 $PAR2", {"$PAR1": 0})

    def test_replacement_value_good_types(self):
        """Test replacement type."""
        source = "par = $PAR"
        cases = [
            ("value", "par = value"),
            (1, "par = 1"),
            (3.14, "par = 3.14"),
        ]

        for value, expected_source in cases:
            with self.subTest(value=value):
                self._awg_module.awg.raw_module.getInt.side_effect = [0, 0, 0]  # successful compilation; get index; upload completed
                self._awg_module.awg.raw_module.getDouble.side_effect = [1.0]  # upload progress

                self.hdawg.compile_and_upload(source, {"$PAR": value})

                expected_calls = [
                    call("compiler/upload", 1),
                    call("compiler/sourcestring", expected_source)
                ]
                self.assertTrue(self.hdawg.compilation_successful())
                self._awg_module.awg.raw_module.set.assert_has_calls(expected_calls)
                self._awg_module.awg.raw_module.set.reset_mock()

    def test_replacement_value_bad_types(self):
        """Test replacement type."""
        with self.assertRaises(ValueError):
            self.hdawg.compile_and_upload("", {"$PAR": None})  # wrong type

        with self.assertRaises(ValueError):
            self.hdawg.compile_and_upload("", {"$PAR": object()})  # wrong type

    def test_compile_error(self):
        """Test failed compile sequence."""
        source = "while(true) {}"
        expected_error = "Compilation did not succeed."
        self._awg_module.awg.raw_module.getInt.side_effect = [1]  # failed compilation

        expected_calls = [
            call("device", _DEVICE_NAME),
            call("index", 0),
            call("compiler/upload", 1),
            call("compiler/sourcestring", source),
        ]
        with self.assertRaises(QMI_RuntimeException) as exc:
            self.hdawg.compile_and_upload(source)

        self._awg_module.awg.raw_module.set.assert_has_calls(expected_calls)
        self.assertFalse(self.hdawg.compilation_successful())
        self.assertEqual(expected_error, str(exc.exception))

    def test_compile_timeout(self):
        """Test timed-out compile sequence."""
        source = "while(true) {}"

        self._awg_module.awg.raw_module.getInt.return_value = -1  # idle

        expected_calls_set = [
            call.awg.raw_module.set("device", _DEVICE_NAME),
            call.awg.raw_module.set("index", 0),
            call.awg.raw_module.set("compiler/upload", 1),
            call.awg.raw_module.set("compiler/sourcestring", source),
        ]
        expected_calls_getint = [
            call.awg.raw_module.getInt("compiler/status"),
            call.awg.raw_module.getInt("compiler/status"),
        ]
        self.hdawg.COMPILE_TIMEOUT = 0.1
        self.hdawg.UPLOAD_TIMEOUT = 0.1
        with self.assertRaises(QMI_TimeoutException):
            self.hdawg.compile_and_upload(source)

        self._awg_module.awg.raw_module.set.assert_has_calls(expected_calls_set)
        self._awg_module.awg.raw_module.getInt.assert_has_calls(expected_calls_getint)
        self._awg_module.awg.raw_module.execute.assert_called_once_with()

    def test_elf_upload_error(self):
        """Test failed ELF upload sequence."""
        source = "while(true) {}"
        expected_exception = "ELF upload did not succeed."
        self._awg_module.awg.raw_module.getInt.side_effect = [2, 2, 1]  # successful compilation; get index; upload timed out
        self._awg_module.awg.raw_module.getDouble.side_effect = [0.3]  # upload progress

        expected_calls_set = [
            call.awg.raw_module.set("device", _DEVICE_NAME),
            call.awg.raw_module.set("index", 0),
            call.awg.raw_module.set("compiler/upload", 1),
            call.awg.raw_module.set("compiler/sourcestring", source),
        ]
        expected_calls_getint = [
            call("compiler/status"),
            call("elf/status"),
        ]

        with self.assertRaises(QMI_RuntimeException) as exc:
            self.hdawg.compile_and_upload(source)

        self.assertEqual(expected_exception, str(exc.exception))
        self._awg_module.awg.raw_module.set.assert_has_calls(expected_calls_set)
        self._awg_module.awg.raw_module.getInt.assert_has_calls(expected_calls_getint)
        self._awg_module.awg.raw_module.getDouble.assert_called_once_with("progress")
        self.assertFalse(self.hdawg.compilation_successful())

    def test_elf_upload_waiting(self):
        """Test failed ELF upload sequence."""
        source = "while(true) {}"
        expected_exception = "ELF upload did not succeed."
        self._awg_module.awg.raw_module.getInt.side_effect = [2, 2, -1]  # successful compilation; get index; upload timed out
        self._awg_module.awg.raw_module.getDouble.side_effect = [0.3]  # upload progress

        expected_calls_set = [
            call.awg.raw_module.set("device", _DEVICE_NAME),
            call.awg.raw_module.set("index", 0),
            call.awg.raw_module.set("compiler/upload", 1),
            call.awg.raw_module.set("compiler/sourcestring", source),
        ]
        expected_calls_getint = [
            call("compiler/status"),
            call("elf/status"),
        ]

        with self.assertRaises(QMI_RuntimeException) as exc:
            self.hdawg.compile_and_upload(source)

        self.assertEqual(expected_exception, str(exc.exception))
        self._awg_module.awg.raw_module.set.assert_has_calls(expected_calls_set)
        self._awg_module.awg.raw_module.getInt.assert_has_calls(expected_calls_getint)
        self._awg_module.awg.raw_module.getDouble.assert_called_once_with("progress")
        self.assertFalse(self.hdawg.compilation_successful())

    def test_elf_upload_timeout(self):
        """Test timed-out ELF upload sequence."""
        upload_progress = [0.0, 0.5]
        self.hdawg.UPLOAD_TIMEOUT = 0.10
        self.hdawg.POLL_PERIOD = 0.05
        source = "while(true) {}"
        expected_exception = f"Upload process timed out (timeout={self.hdawg.UPLOAD_TIMEOUT}) at {upload_progress[1] * 100}%"
        self._awg_module.awg.raw_module.getInt.return_value = 2  # UploadStatus 2 = Busy
        self._awg_module.awg.raw_module.getDouble.side_effect = upload_progress

        expected_calls_set = [
            call.awg.raw_module.set("device", _DEVICE_NAME),
            call.awg.raw_module.set("index", 0),
            call.awg.raw_module.set("compiler/upload", 1),
            call.awg.raw_module.set("compiler/sourcestring", source),
        ]
        expected_calls_getint = [
            call("compiler/status"),
            call("elf/status"),
        ]
        expected_calls_getdouble = [call("progress"), call("progress")]

        with self.assertRaises(QMI_TimeoutException) as exc:
            self.hdawg.compile_and_upload(source)

        self.assertEqual(expected_exception, str(exc.exception))
        self._awg_module.awg.raw_module.set.assert_has_calls(expected_calls_set)
        self._awg_module.awg.raw_module.getInt.assert_has_calls(expected_calls_getint)
        self._awg_module.awg.raw_module.getDouble.assert_has_calls(expected_calls_getdouble)
        self.assertFalse(self.hdawg.compilation_successful())

    def test_upload_sequencer_program(self):
        """Test uploading sequencer program."""
        channel = 4
        program = "Very short program"
        node_mock = self.hdawg.awg_channel_map[channel]
        node_mock.load_sequencer_program.return_value = ({"messages": ""})

        self.hdawg.upload_sequencer_program(channel, program)

        node_mock.load_sequencer_program.assert_called_once_with(program)

    def test_upload_sequencer_program_fails(self):
        """Test exception on uploading sequencer program."""
        channel = 6
        program = "Too short program"
        expected_exception = "Loading sequencer program failed."

        node_mock = self.hdawg.awg_channel_map[channel]
        node_mock.load_sequencer_program.return_value = ({"messages": "I failed :("})

        with self.assertRaises(QMI_RuntimeException) as run_err:
            self.hdawg.upload_sequencer_program(channel, program)

        self.assertEqual(expected_exception, str(run_err.exception))
        node_mock.load_sequencer_program.assert_called_once_with(program)

    def test_compile_sequencer_program(self):
        """Test compiling sequencer program."""
        channel = 4
        program = "Very short program"
        node_mock = self.hdawg.awg_channel_map[channel]
        node_mock.compile_sequencer_program.return_value = (program.encode(), {})

        _, __ = self.hdawg.compile_sequencer_program(channel, program)

        node_mock.compile_sequencer_program.assert_called_once_with(program)

    def test_upload_compiled_program(self):
        """Test uploading a compiled program."""
        channel = 6
        comp_prog = b"Compiled Very short program"
        node_mock = self.hdawg.awg_channel_map[channel]

        _ = self.hdawg.upload_compiled_program(channel, comp_prog)

        node_mock.elf.data.assert_called_once_with(comp_prog)

    def test_get_sequence_snippet(self):
        """Test getting a sequence snippet"""
        expected_snippet = "snippy-snip"
        waveforms_mock = WaveformMock()

        snippet = self.hdawg.get_sequence_snippet(waveforms_mock)

        self.assertEqual(expected_snippet, snippet)

    def test_upload_waveform(self):
        """Test waveform upload. Here also lists happen to work if all three are defined.
        Also the 'assert_has_calls' works directly as the forwarded parameters are still lists.
        """
        core = 0
        index = 0
        wave1 = [1, 2, 3]
        wave2 = [4, 5, 6]
        markers = [7, 8, 9]

        expected_call = call().__setitem__(index, (wave1, wave2, markers))
        core_0 = self.hdawg.awg_channel_map[core]

        with unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.Waveforms"
        ) as waveforms_patch:
            self.hdawg.upload_waveform(core, index, wave1, wave2, markers)

        core_0.write_to_waveform_memory.assert_called_once_with(waveforms_patch())
        expected_daq_server_calls = [
            call.setInt(f"/{_DEVICE_NAME}/system/awg/channelgrouping", 2)
        ]
        self._daq_server.assert_has_calls(expected_daq_server_calls)
        waveforms_patch.assert_has_calls([expected_call], any_order=True)
        waveforms_patch().validate.assert_called_once()  # When creating the 'waveform'.

    def test_upload_complex_waveform(self):
        """Test waveform upload where wave1 is a complex wave and gets split in
        real and imaginary parts when wave2 is None."""
        core = 0
        index = 0
        wave1 = np.array([1 + 0j, 2 + 1j, 3 + 0j])
        wave2 = None
        markers = np.array([7, 8, 9])

        core_0 = self.hdawg.awg_channel_map[core]

        with unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.Waveforms"
        ) as waveforms_patch:
            self.hdawg.upload_waveform(core, index, wave1, wave2, markers)

        core_0.write_to_waveform_memory.assert_called_once_with(waveforms_patch())
        expected_daq_server_calls = [
            call.setInt(f"/{_DEVICE_NAME}/system/awg/channelgrouping", 2)
        ]
        self._daq_server.assert_has_calls(expected_daq_server_calls)
        call_made = waveforms_patch.mock_calls[1]
        self.assertEqual(index, call_made[1][0])
        npt.assert_array_equal(wave1.real, call_made[1][1][0])
        npt.assert_array_equal(wave1.imag, call_made[1][1][1])
        npt.assert_array_equal(markers, call_made[1][1][2])
        waveforms_patch().validate.assert_called_once()  # When creating the 'waveform'.

    def test_upload_waveforms_small_batch(self):
        """Test uploading a small batch of waveforms (less than batch size limit)."""
        unpacked_waveforms = []
        batch_size = 10
        for i in range(batch_size):
            awg_index = i % 4
            waveform_index = i
            wave1 = np.array([i + 1, i + 2, i + 3])
            wave2 = np.array([i + 4, i + 5, i + 6]) if i % 2 else None
            markers = np.array([i + 7, i + 8, i + 9]) if i % 2 else None
            unpacked_waveforms.append((awg_index, waveform_index, wave1, wave2, markers))

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst.utils"
            ) as utils_patch:
            self.hdawg.upload_waveforms(unpacked_waveforms)

        expected_utils_calls = [
            call.convert_awg_waveform(unpacked_waveforms[i][:3]) for i in range(batch_size)
        ]

        expected_daq_server_calls = [
            call.setVector(f"/{_DEVICE_NAME}/awgs/{i%4}/waveform/waves/{i}", "WAVEFORM") for i in range(batch_size)
        ]
        [self._daq_server.assert_has_calls(c[2]) for c in expected_daq_server_calls]
        self._daq_server.set.assert_called_once()
        [utils_patch.assert_has_calls(c[2]) for c in expected_utils_calls]

    def test_upload_waveforms_large_batch(self):
        """Test uploading a 'large' batch of waveforms (more than batch size limit but exact multiple of)."""
        unpacked_waveforms = []
        batch_size = 30
        for i in range(batch_size):
            awg_index = i % 4
            waveform_index = i
            wave1 = np.array([i + 1, i + 2, i + 3])
            wave2 = np.array([i + 4, i + 5, i + 6])
            markers = np.array([i + 7, i + 8, i + 9])
            unpacked_waveforms.append((awg_index, waveform_index, wave1, wave2, markers))

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst.utils"
            ) as utils_patch:
            self.hdawg.upload_waveforms(unpacked_waveforms, batch_size=batch_size // 3)

        expected_utils_calls = [
            call.convert_awg_waveform(unpacked_waveforms[i][:3]) for i in range(batch_size)
        ]

        expected_daq_server_calls = [
            call.setVector(f"/{_DEVICE_NAME}/awgs/{i%4}/waveform/waves/{i}", "WAVEFORM") for i in range(batch_size)
        ]
        [self._daq_server.assert_has_calls(c[2]) for c in expected_daq_server_calls]
        self.assertEqual(self._daq_server.set.call_count, batch_size / 10)
        [utils_patch.assert_has_calls(c[2]) for c in expected_utils_calls]

    def test_upload_waveforms_large_batch_2(self):
        """Test uploading a 'large' batch of waveforms (more than batch size limit and not exact multiple of)."""
        unpacked_waveforms = []
        batch_size = 31
        for i in range(batch_size):
            awg_index = i % 4
            waveform_index = i
            wave1 = np.array([i + 1, i + 2, i + 3])
            wave2 = np.array([i + 4, i + 5, i + 6])
            markers = np.array([i + 7, i + 8, i + 9])
            unpacked_waveforms.append((awg_index, waveform_index, wave1, wave2, markers))

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst.utils"
            ) as utils_patch:
            self.hdawg.upload_waveforms(unpacked_waveforms, batch_size=batch_size // 3)

        expected_utils_calls = [
            call.convert_awg_waveform(unpacked_waveforms[i][:3]) for i in range(batch_size)
        ]

        expected_daq_server_calls = [
            call.setVector(f"/{_DEVICE_NAME}/awgs/{i%4}/waveform/waves/{i}", "WAVEFORM") for i in range(batch_size)
        ]
        [self._daq_server.assert_has_calls(c[2]) for c in expected_daq_server_calls]
        self.assertEqual(self._daq_server.set.call_count, np.ceil(batch_size / 10))
        [utils_patch.assert_has_calls(c[2]) for c in expected_utils_calls]

    def test_write_to_waveform_memory(self):
        """Test writing to waveform memory with and without indexes"""
        channel = 5
        node_mock = self.hdawg.awg_channel_map[channel]
        wf_mock = Mock()
        # No indexes test
        self.hdawg.write_to_waveform_memory(channel, wf_mock, None)

        node_mock.write_to_waveform_memory.assert_called_once_with(wf_mock)
        node_mock.reset_mock()

        # With indexes test
        indexes = [0, 2]
        self.hdawg.write_to_waveform_memory(channel, wf_mock, indexes)

        node_mock.write_to_waveform_memory.assert_called_once_with(wf_mock, indexes)

    def test_read_from_waveform_memory(self):
        """Test reading from waveform memory with and without indexes."""
        channel = 6
        node_mock = self.hdawg.awg_channel_map[channel]
        # No indexes test
        _ = self.hdawg.read_from_waveform_memory(channel, None)

        node_mock.read_from_waveform_memory.assert_called_once_with()
        node_mock.reset_mock()

        # With indexes test
        indexes = [0, 2]
        self.hdawg.read_from_waveform_memory(channel, indexes)

        node_mock.read_from_waveform_memory.assert_called_once_with(indexes)

    def test_upload_waveforms_per_awg_core(self):
        """Test uploading a 'large' batch of waveforms (more than batch size limit but exact multiple of)."""
        unpacked_waveforms = []
        batch_size = 30
        for i in range(batch_size):
            awg_index = i % 4
            waveform_index = i
            wave1 = np.array([i + 1, i + 2, i + 3])
            wave2 = np.array([i + 4, i + 5, i + 6])
            markers = np.array([i + 7, i + 8, i + 9])
            unpacked_waveforms.append((awg_index, waveform_index, wave1, wave2, markers))

        core_mock_0 = self._device.awgs[0]
        core_mock_1 = self._device.awgs[1]
        core_mock_2 = self._device.awgs[2]
        core_mock_3 = self._device.awgs[3]
        with unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst"
        ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst.utils"
        ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.Waveforms"
        ) as wf_patch:
            self.hdawg.upload_waveforms_per_awg_core(unpacked_waveforms)

        core_mock_0.write_to_waveform_memory.assert_called_with(wf_patch())
        core_mock_1.write_to_waveform_memory.assert_called_with(wf_patch())
        core_mock_2.write_to_waveform_memory.assert_called_with(wf_patch())
        core_mock_3.write_to_waveform_memory.assert_called_with(wf_patch())

    def test_get_schema(self):
        """Test getting a schema for a channel."""
        channel = 0
        node_mock = self.hdawg.awg_channel_map[channel]

        _ = self.hdawg.get_schema(channel)

        node_mock.commandtable.load_validation_schema.assert_called_once_with()

    def test_get_command_table(self):
        """Test getting a command table for a channel."""
        channel = 0
        node_mock = self.hdawg.awg_channel_map[channel]

        _ = self.hdawg.get_command_table(channel)

        node_mock.commandtable.load_from_device.assert_called_once_with()

    def test_upload_command_table(self):
        """Test command table upload."""
        command_table_entries = [
            {
                "index": 1,
                "waveform": {
                    "playZero": True,
                    "length": 128
                }
            }
        ]

        with unittest.mock.patch("builtins.open", unittest.mock.mock_open()), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst"
        ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst.toolkit"
        ) as zhinst_patch:
            zhinst_patch.CommandTable = Mock(return_value=self.CommandTableMock)
            with unittest.mock.patch(
                    "qmi.instruments.zurich_instruments.hdawg.json", spec=json
                ) as json_patch, unittest.mock.patch(
                    "qmi.instruments.zurich_instruments.hdawg.jsonschema", spec=jsonschema
            ) as schema_patch:
                json_patch.loads = Mock(
                    return_value=json.loads(_SCHEMA["/DEV8888/awgs/0/commandtable/schema"][0]["vector"])
                )
                json_patch.dumps = Mock()
                schema_patch.validate = Mock()
                self.hdawg.upload_command_table(0, command_table_entries, save_as_file=True)

        zhinst_patch.CommandTable.assert_called_once()
        # Assert that only index 1 was changed, as intended
        for n, entry in enumerate(self.CommandTableMock.table):
            if n != command_table_entries[0]["index"]:
                self.assertEqual(0, entry.waveform.length)
                self.assertFalse(entry.waveform.playZero)
            else:
                self.assertEqual(command_table_entries[0]["waveform"]["length"], entry.waveform.length)
                self.assertTrue(entry.waveform.playZero)

        zhinst_patch.CommandTable.reset_mock()

    def test_upload_empty_command_table(self):
        """Test empty command table upload."""
        table = []
        awg_index = 0

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
        ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst.toolkit"
        ) as zhinst_patch:
            zhinst_patch.CommandTable = Mock(return_value=self.CommandTableMock)
            self.hdawg.upload_command_table(awg_index, table)

        zhinst_patch.CommandTable.assert_called_once()
        # Assert that all indexes have not been changed.
        for n, entry in enumerate(self.CommandTableMock.table):
            self.assertEqual(0, entry.waveform.length)
            self.assertFalse(entry.waveform.playZero)

        zhinst_patch.CommandTable.reset_mock()

    def test_upload_invalid_command_table(self):
        """Test invalid command table upload."""
        command_table_entries = [
            {
                "index": 1,
                "waveform": {
                    "playZero": True,
                    "length": 123  # must be multiple of 16
                }
            }
        ]
        core = 0
        expected_runtime_error = f"The upload of command table on core {core} failed."
        expected_validation_error = "Invalid command table."
        expected_value_error = "Invalid value in command table."

        with unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst"
        ), unittest.mock.patch.object(
            qmi.instruments.zurich_instruments.hdawg.zhinst.toolkit.exceptions, "ValidationError", ValidationError
        ):
            self._device.awgs[0].commandtable.upload_to_device.side_effect = [
                RuntimeError("Run b4 they Findus!"), ValidationError("Invalid")
            ]
            with self.assertRaises(RuntimeError) as r_err:
                self.hdawg.upload_command_table(core, command_table_entries)

            with self.assertRaises(ValueError) as v_err:
                self.hdawg.upload_command_table(core, command_table_entries)

            with unittest.mock.patch(
                    "qmi.instruments.zurich_instruments.hdawg.json", spec=json
                ) as json_patch, unittest.mock.patch(
                    "qmi.instruments.zurich_instruments.hdawg.jsonschema", spec=jsonschema
            ) as schema_patch:
                json_patch.loads = Mock(return_value=json.loads(_SCHEMA["/DEV8888/awgs/0/commandtable/schema"][0]["vector"]))
                json_patch.dumps = Mock(side_effect=[TypeError("Ugly value")])
                schema_patch.validate = Mock()
                with self.assertRaises(ValueError) as v_err_2:
                    self.hdawg.upload_command_table(core, command_table_entries, save_as_file=True)

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.json", spec=json
            ) as json_patch, unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.jsonschema", spec=jsonschema
        ) as schema_patch:
            json_patch.loads = Mock(return_value=json.loads(_SCHEMA["/DEV8888/awgs/0/commandtable/schema"][0]["vector"]))
            json_patch.dumps = Mock(side_effect=[TypeError("Ugly value")])
            schema_patch.validate = Mock()

        self.assertEqual(expected_runtime_error, str(r_err.exception))
        self.assertEqual(expected_validation_error, str(v_err.exception))
        self.assertEqual(expected_value_error, str(v_err_2.exception))

    def test_upload_command_table_wrong_awg(self):
        """Test invalid command table upload."""
        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
        ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst.toolkit"
        ):
            with self.assertRaises(ValueError):
                self.hdawg.upload_command_table(-1, [])

            with self.assertRaises(ValueError):
                self.hdawg.upload_command_table(4, [])

    def test_sync(self):
        """Test sync method."""
        self.hdawg.sync()

        self.hdawg._session.sync.assert_called_once_with()

    def test_enable_sequencer(self):
        """Test enabling sequencer on specific channel."""
        channel_1 = 3
        channel_2 = 7

        node_mock_1 = self.hdawg.awg_channel_map[channel_1]
        node_mock_2 = self.hdawg.awg_channel_map[channel_2]

        self.hdawg.enable_sequencer(channel_1)
        node_mock_1.enable_sequencer.assert_called_once_with(single=True)
        node_mock_1.reset_mock()

        self.hdawg.enable_sequencer(channel_2, False)
        node_mock_2.enable_sequencer.assert_called_once_with(single=False)

    def test_channel_ready(self):
        """Test channel_ready when it is ready."""
        channel = 2
        node_mock = self.hdawg.awg_channel_map[channel]

        ready = self.hdawg.channel_ready(channel)

        node_mock.ready.assert_called_once_with()
        self.assertTrue(ready)

    def test_channel_ready_excepts(self):
        """Test channel_ready when it is ready."""
        channel = 2
        node_mock = self.hdawg.awg_channel_map[channel]
        node_mock.ready.return_value = False
        self.hdawg.COMPILE_TIMEOUT = 0.05
        self.hdawg.UPLOAD_TIMEOUT = 0.05
        self.hdawg.POLL_PERIOD = 0.05

        not_ready = self.hdawg.channel_ready(channel)

        self.assertFalse(not_ready)

    def test_wait_done(self):
        """Test wait_done call."""
        channel = 6
        timeout = 0.0
        channel_mock = self.hdawg.awg_channel_map[channel]

        self.hdawg.wait_done(channel, timeout)

        channel_mock.wait_done.assert_called_once_with(timeout=timeout)

    def test_get_awg_module_index(self):
        """Test gettings AWG module index."""
        self._awg_module.awg.raw_module.getInt.return_value = 3

        index = self.hdawg.get_awg_module_index()

        self._awg_module.awg.raw_module.getInt.assert_called_once_with("index")
        self.assertEqual(3, index)

    def test_set_awg_module_index(self):
        """Test setting AWG module index with good values."""
        side_effect = [True, False] * 7  # group 0 = 4x, group 1 = 2x, group 2 = 1x
        self._awg_module.finished.side_effect = side_effect + [False, True]  # For close
        groupings = list(range(3))
        for grouping in groupings:
            self.hdawg._grouping = grouping
            ok_indexes = list(range((2 - grouping) * 2))
            ok_indexes = [0] if not ok_indexes else ok_indexes
            for index in ok_indexes:
                self.hdawg.set_awg_module_index(index)

    def test_set_awg_module_index_exceptions(self):
        """Test setting AWG module index with wrong values w.r.t. grouping."""
        self._awg_module.finished.side_effect = [False, True]  # For close
        nok_indexes = [-1, 4]
        for index in nok_indexes:
            with self.assertRaises(ValueError):
                self.hdawg.set_awg_module_index(index)

    def test_get_awg_core_enabled(self):
        """Test getting AWG core enable state."""
        self.hdawg.get_awg_core_enabled(0)
        self._device.awgs[0].enable.assert_called_once_with()
        self._device.reset_mock()
        self.hdawg.get_awg_core_enabled(3)
        self._device.awgs[3].enable.assert_called_once_with()

    def test_get_awg_core_enabled_invalid_cores(self):
        """Test getting AWG core enable states with wrong core numbers"""
        with self.assertRaises(ValueError):
            self.hdawg.get_awg_core_enabled(9)

        with self.assertRaises(ValueError):
            self.hdawg.get_awg_core_enabled(-1)

    def test_set_awg_core_enabled(self):
        """Test AWG core enable on/off."""
        self.hdawg.set_awg_core_enabled(0, 1)
        self._device.awgs[0].enable.assert_called_once_with(1)
        self._device.reset_mock()
        self.hdawg.set_awg_core_enabled(3, 0)
        self._device.awgs[3].enable.assert_called_once_with(0)

    def test_set_awg_core_enabled_invalid_values(self):
        """Test AWG core enable on/off with invalid inputs"""
        with self.assertRaises(ValueError):
            self.hdawg.set_awg_core_enabled(9, 1)

        with self.assertRaises(ValueError):
            self.hdawg.set_awg_core_enabled(0, 3)

    def test_get_awg_module_enabled(self):
        self.hdawg.get_awg_module_enabled()
        self.hdawg.awg_module.getInt.assert_called_once_with("awg/enable")

    def test_set_awg_module_enabled(self):
        expected_awg_module_calls = [
            call("awg/enable", 0),
            call("awg/enable", 1),
        ]

        self._awg_module.reset_mock()
        self.hdawg.set_awg_module_enabled(0)
        self.hdawg.set_awg_module_enabled(1)

        self._awg_module.awg.raw_module.set.assert_has_calls(expected_awg_module_calls)

        with self.assertRaises(ValueError):
            self.hdawg.set_awg_module_enabled(-1)

        with self.assertRaises(ValueError):
            self.hdawg.set_awg_module_enabled(2)

    def test_get_channel_grouping(self):
        """Test setting channel grouping."""
        self._daq_server.getInt.return_value = 1

        grouping = self.hdawg.get_channel_grouping()

        self._check_get_value_int("system/awg/channelgrouping")
        self.assertEqual(1, grouping)

    def test_set_channel_grouping(self):
        """Test setting channel grouping."""
        self.hdawg.set_channel_grouping(0)
        self._check_set_value_int("system/awg/channelgrouping", 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_channel_grouping(3)

    def test_set_reference_clock_source(self):
        """Test reference clock source setting."""
        self.hdawg.set_reference_clock_source(0)
        self._device.system.clocks.referenceclock.source.assert_called_once_with(0)
        self.hdawg.set_reference_clock_source(1)
        self._device.system.clocks.referenceclock.source.assert_called_with(1)
        self.hdawg.set_reference_clock_source(2)
        self._device.system.clocks.referenceclock.source.assert_called_with(2)

        with self.assertRaises(ValueError):
            self.hdawg.set_reference_clock_source(3)

    def test_get_reference_clock_status(self):
        """Test reference clock source status."""
        self.hdawg.get_reference_clock_status()
        self._device.system.clocks.referenceclock.status.assert_called_once_with()

    def test_set_sample_clock_frequency(self):
        """"Test sample clock setting."""
        self.hdawg.set_sample_clock_frequency(1234.5e6)
        self._device.system.clocks.sampleclock.freq.assert_called_once_with(1234.5e6)

    def test_get_sample_clock_status(self):
        """Test reference clock source status."""
        self.hdawg.get_sample_clock_status()
        self._device.system.clocks.sampleclock.status.assert_called_once_with()

    def test_set_trigger_impedance(self):
        """Test trigger impedance setting."""
        self.hdawg.set_trigger_impedance(0, 0)
        self._device.triggers.in_[0].imp50.assert_called_once_with(0)
        self.hdawg.set_trigger_impedance(0, 1)
        self._device.triggers.in_[0].imp50.assert_called_with(1)
        self.hdawg.set_trigger_impedance(7, 0)
        self._device.triggers.in_[7].imp50.assert_called_with(0)
        self.hdawg.set_trigger_impedance(7, 1)
        self._device.triggers.in_[7].imp50.assert_called_with(1)

        with self.assertRaises(ValueError):
            self.hdawg.set_trigger_impedance(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_trigger_impedance(8, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_trigger_impedance(0, 2)

        with self.assertRaises(ValueError):
            self.hdawg.set_trigger_impedance(8, 2)

    def test_get_trigger_level(self):
        """test getting a trigger level."""
        trigger = 1

        self.hdawg.get_trigger_level(trigger)

        self._device.triggers.in_[trigger].level.assert_called_once_with()

    def test_get_trigger_level_excepts(self):
        """test getting a trigger level with invalid trigger numbers."""
        triggers = [-1, self.hdawg.NUM_CHANNELS]

        for trigger in triggers:
            with self.assertRaises(ValueError):
                self.hdawg.get_trigger_level(trigger)

    def test_set_trigger_level(self):
        """Test trigger level setting."""
        triggers = [0, 7]
        levels = [-5.0, 0, 5.0]
        for trigger, level in zip(triggers, levels):
            self._device.reset_mock()
            self.hdawg.set_trigger_level(trigger, level)
            self._device.triggers.in_[trigger].level.assert_called_once_with(level)

        with self.assertRaises(ValueError):
            self.hdawg.set_trigger_level(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_trigger_level(8, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_trigger_level(0, 10.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_trigger_level(0, -10.0)

    def test_set_marker_source(self):
        """Test marker setting."""
        # NOTE: 16 is invalid value
        for i in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17, 18):
            self.hdawg.set_marker_source(0, i)
            self._check_set_value_int("triggers/out/0/source", i)

        self.hdawg.set_marker_source(7, 0)
        self._check_set_value_int("triggers/out/7/source", 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_marker_source(0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.set_marker_source(0, 16)

        with self.assertRaises(ValueError):
            self.hdawg.set_marker_source(0, 19)

        with self.assertRaises(ValueError):
            self.hdawg.set_marker_source(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_marker_source(8, 0)

    def test_set_marker_delay(self):
        """Test marker delay."""
        self.hdawg.set_marker_delay(0, 0.0)
        self._check_set_value_double("triggers/out/0/delay", 0.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_marker_delay(-1, 0.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_marker_delay(8, 0.0)

    def test_set_dig_trigger_source(self):
        """Test digital trigger source setting."""
        cores = [0, 3]
        triggers = [0, 1]
        for core, trigger in zip(cores, triggers):
            self._device.reset_mock()
            self.hdawg.set_dig_trigger_source(core, trigger, core * 2)
            self._device.awgs[core].auxtriggers[trigger].channel.assert_called_once_with(core * 2)

        with self.assertRaises(ValueError):
            self.hdawg.set_dig_trigger_source(-1, 0, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dig_trigger_source(4, 0, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dig_trigger_source(0, -1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dig_trigger_source(0, 2, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dig_trigger_source(0, 0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.set_dig_trigger_source(0, 0, 8)

    def test_set_dig_trigger_slope(self):
        """Test digital trigger slope setting."""
        cores = [0, 3]
        triggers = [0, 1]
        for core, trigger in zip(cores, triggers):
            self._device.reset_mock()
            self.hdawg.set_dig_trigger_slope(core, trigger, core)
            self._device.awgs[core].auxtriggers[trigger].slope.assert_called_once_with(core)

        with self.assertRaises(ValueError):
            self.hdawg.set_dig_trigger_slope(-1, 0, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dig_trigger_slope(4, 0, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dig_trigger_slope(0, -1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dig_trigger_slope(0, 2, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dig_trigger_slope(0, 0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.set_dig_trigger_slope(0, 0, 4)

    def test_get_output_gain(self):
        """Test output gain query."""
        channels = [0, 7]
        for channel in channels:
            gain_index = channel % 2
            gain = self.hdawg.get_output_gain(channel, gain_index)
            print(f"{gain=}")
            core = channel // 2
            output = channel % 2
            self._check_get_value_double(f"awgs/{core}/outputs/{output}/gains/{gain_index}")
            self.assertEqual(gain, self._daq_server.getDouble())

        # Test without gain_index input
        channel_x = 4
        gain = self.hdawg.get_output_gain(channel_x)
        core = channel_x // 2
        output = channel_x % 2
        self._check_get_value_double(f"awgs/{core}/outputs/{output}/gains/0")

        with self.assertRaises(ValueError):
            self.hdawg.get_output_gain(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.get_output_gain(8, 0)

        with self.assertRaises(ValueError):
            self.hdawg.get_output_gain(0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.get_output_gain(0, 3)

    def test_get_output_gain_both(self):
        """Test output gain query obtaining both values."""
        channels = [0, 7]
        gain_index = 2
        for channel in channels:
            gains = self.hdawg.get_output_gain(channel, gain_index)
            core = channel // 2
            output = channel % 2
            print(f"{gains=}")
            self.assertEqual(2, len(gains))
            self._check_get_value_double(f"awgs/{core}/outputs/{output}/gains/0")
            self._check_get_value_double(f"awgs/{core}/outputs/{output}/gains/1")

    def test_set_output_gain(self):
        """Test output gain setting."""
        channels = [0, 7]
        for channel in channels:
            gain_index = channel % 2
            self._device.reset_mock()
            self.hdawg.set_output_gain(channel, 0.1 * channel, gain_index)
            core = channel // 2
            output = channel % 2
            self._check_set_value_double(f"awgs/{core}/outputs/{output}/gains/{gain_index}", 0.1 * channel)

        # Test without setting gain index
        channel_x = 4
        self.hdawg.set_output_gain(channel_x, 0.1 * channel_x)
        core = channel_x // 2
        output = channel_x % 2
        self._check_set_value_double(f"awgs/{core}/outputs/{output}/gains/0", 0.1 * channel_x)

        # Test list input gains, but only one gain set
        channels = [0, 5]
        for channel in channels:
            gain_index = channel % 2
            gains = [0.1 * channel, 0.2 * channel]
            self._device.reset_mock()
            self.hdawg.set_output_gain(channel, gains, gain_index)
            core = channel // 2
            output = channel % 2
            self._check_set_value_double(f"awgs/{core}/outputs/{output}/gains/{gain_index}", gains[gain_index])

        with self.assertRaises(ValueError):
            self.hdawg.set_output_gain(-1, 1.0, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_gain(8, 1.0, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_gain(0, 1.0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_gain(0, 1.0, 3)

    def test_set_output_gain_both(self):
        """Test output gain setting for both indexes."""
        channels = [0, 7]
        for channel in channels:
            self._device.reset_mock()
            self.hdawg.set_output_gain(channel, 0.1 * channel, 2)
            core = channel // 2
            output = channel % 2
            self._check_set_value_double(f"awgs/{core}/outputs/{output}/gains/0", 0.1 * channel)
            self._check_set_value_double(f"awgs/{core}/outputs/{output}/gains/1", 0.1 * channel)

        channel_x = 4
        gains = [0.1 * channel_x, 0.2 * channel_x]
        self.hdawg.set_output_gain(channel_x, gains, 2)

    def test_get_output_channel_hold(self):
        """Test output hold query."""
        for channel in [0, 7]:
            core = channel // 2
            output = channel % 2
            self.hdawg.get_output_channel_hold(channel)
            self._check_get_value_int(f"awgs/{core}/outputs/{output}/hold")

        with self.assertRaises(ValueError):
            self.hdawg.get_output_channel_hold(-1)

        with self.assertRaises(ValueError):
            self.hdawg.get_output_channel_hold(8)

    def test_set_output_channel_hold(self):
        """Test output hold setting."""
        channels = [0, 7]
        holds = [0, 1]
        for channel, hold in zip(channels, holds):
            core = channel // 2
            output = channel % 2
            self.hdawg.set_output_channel_hold(channel, hold)
            self._check_set_value_int(f"awgs/{core}/outputs/{output}/hold", hold)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_hold(-1, 1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_hold(8, 1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_hold(0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_hold(0, 2)

    def test_get_output_channel_on(self):
        """Test output channel on/off state query."""
        self.hdawg.get_output_channel_on(0)
        self._check_get_value_int("sigouts/0/on")
        self.hdawg.get_output_channel_on(7)
        self._check_get_value_int("sigouts/7/on")

        with self.assertRaises(ValueError):
            self.hdawg.get_output_channel_on(-1)

        with self.assertRaises(ValueError):
            self.hdawg.get_output_channel_on(8)

    def test_set_output_channel_on(self):
        """Test output channel on/off switching."""
        self.hdawg.set_output_channel_on(0, 0)
        self._check_set_value_int("sigouts/0/on", 0)
        self.hdawg.set_output_channel_on(0, 1)
        self._check_set_value_int("sigouts/0/on", 1)
        self.hdawg.set_output_channel_on(7, 0)
        self._check_set_value_int("sigouts/7/on", 0)
        self.hdawg.set_output_channel_on(7, 1)
        self._check_set_value_int("sigouts/7/on", 1)

    def test_set_output_channel_on_valueerror(self):
        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_on(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_on(8, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_on(0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_on(0, 2)

    def test_set_output_channel_range(self):
        """Test output channel range setting."""
        valid_values = [0.2, 2, 5]
        for value in valid_values:
            self.hdawg.set_output_channel_range(0, value)
            self._check_set_value_double("sigouts/0/range", value)
            self.hdawg.set_output_channel_range(7, value)
            self._check_set_value_double("sigouts/7/range", value)

    def test_set_output_channel_range_out_of_range(self):
        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_range(-1, 0.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_range(8, 0.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_range(0, -1.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_range(0, 6.0)

    def test_set_output_channel_offset(self):
        """Test output channel offset setting."""
        self.hdawg.set_output_channel_offset(0, 0.0)
        self._check_set_value_double("sigouts/0/offset", 0.0)
        self.hdawg.set_output_channel_offset(0, 1.25)
        self._check_set_value_double("sigouts/0/offset", 1.25)
        self.hdawg.set_output_channel_offset(0, -1.25)
        self._check_set_value_double("sigouts/0/offset", -1.25)
        self.hdawg.set_output_channel_offset(7, 0.0)
        self._check_set_value_double("sigouts/7/offset", 0.0)
        self.hdawg.set_output_channel_offset(7, 1.25)
        self._check_set_value_double("sigouts/7/offset", 1.25)
        self.hdawg.set_output_channel_offset(7, -1.25)
        self._check_set_value_double("sigouts/7/offset", -1.25)

    def test_set_output_channel_offset_out_of_range(self):
        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_offset(-1, 0.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_offset(8, 0.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_offset(0, -2.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_offset(0, 2.0)

    def test_get_output_channel_delay(self):
        """Test getting output channel delay."""
        self.hdawg.get_output_channel_delay(0)
        self._check_get_value_float("sigouts/0/delay")
        self.hdawg.get_output_channel_delay(7)
        self._check_get_value_float("sigouts/7/delay")

        with self.assertRaises(ValueError):
            self.hdawg.get_output_channel_delay(-1)

        with self.assertRaises(ValueError):
            self.hdawg.get_output_channel_delay(8)

    def test_set_output_channel_delay(self):
        """Test output channel delay setting."""
        self.hdawg.set_output_channel_delay(0, 0.0)
        self._check_set_value_double("sigouts/0/delay", 0.0)
        self.hdawg.set_output_channel_delay(0, 25e-9)
        self._check_set_value_double("sigouts/0/delay", 25e-9)
        self.hdawg.set_output_channel_delay(7, 0.0)
        self._check_set_value_double("sigouts/7/delay", 0.0)
        self.hdawg.set_output_channel_delay(7, 25e-9)
        self._check_set_value_double("sigouts/7/delay", 25e-9)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_delay(-1, 0.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_delay(8, 0.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_delay(0, -1.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_delay(0, 1.0)

    def test_set_output_channel_direct(self):
        """Test output channel direct setting."""
        self.hdawg.set_output_channel_direct(0, 0)
        self._check_set_value_int("sigouts/0/direct", 0)
        self.hdawg.set_output_channel_direct(0, 1)
        self._check_set_value_int("sigouts/0/direct", 1)
        self.hdawg.set_output_channel_direct(7, 0)
        self._check_set_value_int("sigouts/7/direct", 0)
        self.hdawg.set_output_channel_direct(7, 1)
        self._check_set_value_int("sigouts/7/direct", 1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_direct(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_direct(8, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_direct(0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_direct(0, 2)

    def test_set_output_channel_filter(self):
        """Test output channel filter setting."""
        self.hdawg.set_output_channel_filter(0, 0)
        self._check_set_value_int("sigouts/0/filter", 0)
        self.hdawg.set_output_channel_filter(0, 1)
        self._check_set_value_int("sigouts/0/filter", 1)
        self.hdawg.set_output_channel_filter(7, 0)
        self._check_set_value_int("sigouts/7/filter", 0)
        self.hdawg.set_output_channel_filter(7, 1)
        self._check_set_value_int("sigouts/7/filter", 1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_filter(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_filter(8, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_filter(0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_filter(0, 2)

    def test_get_dio_mode(self):
        """Test getting DIO mode."""
        _ = self.hdawg.get_dio_mode()

        self.hdawg.device.dios[0].mode.assert_called_once_with()

    def test_set_dio_mode(self):
        """Test DIO mode setting."""
        for i in range(4):
            self._device.reset_mock()
            self.hdawg.set_dio_mode(i)
            self._device.dios[0].mode.assert_called_once_with(i)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_mode(-1)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_mode(4)

    def test_set_dio_drive(self):
        """Test DIO drive setting."""
        for i in range(16):
            self._device.reset_mock()
            self.hdawg.set_dio_drive(i)
            self._device.dios[0].drive.assert_called_once_with(i)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_drive(-1)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_drive(16)

    def test_set_digital_output(self):
        """Test setting all digital channels as outputs."""
        dio = self.hdawg.device.dios[0]

        self.hdawg.set_digital_output(True)

        dio.output.assert_called_once_with(1)
        dio.reset_mock()

        self.hdawg.set_digital_output(0)

        dio.output.assert_called_once_with(0)

    def test_set_dio_valid_index(self):
        """Test DIO VALID signal index setting."""
        core_0 = self.hdawg.awg_channel_map[0]
        core_3 = self.hdawg.awg_channel_map[3]

        self.hdawg.set_dio_valid_index(0, 0)
        self.hdawg.set_dio_valid_index(0, 31)
        self.hdawg.set_dio_valid_index(3, 0)
        self.hdawg.set_dio_valid_index(3, 31)

        core_0.dio.valid.index.assert_has_calls(
            [call(0), call(31)]
        )
        core_3.dio.valid.index.assert_has_calls(
            [call(0), call(31)]
        )

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_valid_index(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_valid_index(4, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_valid_index(0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_valid_index(0, 32)

    def test_set_dio_polarity(self):
        """Test DIO polarity setting."""
        core_0 = self.hdawg.awg_channel_map[0]
        core_3 = self.hdawg.awg_channel_map[3]
        self.hdawg.set_dio_polarity(0, 0)
        self.hdawg.set_dio_polarity(0, 3)
        self.hdawg.set_dio_polarity(3, 0)
        self.hdawg.set_dio_polarity(3, 3)

        core_0.dio.valid.polarity.assert_has_calls(
            [call(0), call(3)]
        )
        core_3.dio.valid.polarity.assert_has_calls(
            [call(0), call(3)]
        )

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_polarity(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_polarity(4, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_polarity(0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_polarity(0, 4)

    def test_set_dio_polarity_with_strings(self):
        """Test DIO polarity setting with string values."""
        core_0 = self.hdawg.awg_channel_map[0]
        core_3 = self.hdawg.awg_channel_map[3]
        self.hdawg.set_dio_polarity(0, "none")
        self.hdawg.set_dio_polarity(0, "both")
        self.hdawg.set_dio_polarity(3, "0")
        self.hdawg.set_dio_polarity(3, "3")

        core_0.dio.valid.polarity.assert_has_calls(
            [call("none"), call("both")]
        )
        core_3.dio.valid.polarity.assert_has_calls(
            [call(0), call(3)]
        )

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_polarity(0, "neither")

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_polarity(0, "-2")

    def test_set_dio_strobe_index(self):
        """Test DIO strobe index setting."""
        self.hdawg.set_dio_strobe_index(0, 0)
        self._check_set_value_int("awgs/0/dio/strobe/index", 0)
        self.hdawg.set_dio_strobe_index(0, 31)
        self._check_set_value_int("awgs/0/dio/strobe/index", 31)
        self.hdawg.set_dio_strobe_index(3, 0)
        self._check_set_value_int("awgs/3/dio/strobe/index", 0)
        self.hdawg.set_dio_strobe_index(3, 31)
        self._check_set_value_int("awgs/3/dio/strobe/index", 31)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_strobe_index(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_strobe_index(4, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_strobe_index(0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_strobe_index(0, 32)

    def test_set_dio_strobe_slope(self):
        """Test DIO strobe slope setting."""
        self.hdawg.set_dio_strobe_slope(0, 0)
        self._check_set_value_int("awgs/0/dio/strobe/slope", 0)
        self.hdawg.set_dio_strobe_slope(0, 3)
        self._check_set_value_int("awgs/0/dio/strobe/slope", 3)
        self.hdawg.set_dio_strobe_slope(3, 0)
        self._check_set_value_int("awgs/3/dio/strobe/slope", 0)
        self.hdawg.set_dio_strobe_slope(3, 3)
        self._check_set_value_int("awgs/3/dio/strobe/slope", 3)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_strobe_slope(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_strobe_slope(4, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_strobe_slope(0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_strobe_slope(0, 4)

    def test_get_user_register(self):
        """Test get user register."""
        self.hdawg.get_user_register(0, 0)
        self._check_get_value_int("awgs/0/userregs/0")
        self.hdawg.get_user_register(0, 15)
        self._check_get_value_int("awgs/0/userregs/15")
        self.hdawg.get_user_register(3, 0)
        self._check_get_value_int("awgs/3/userregs/0")
        self.hdawg.get_user_register(3, 15)
        self._check_get_value_int("awgs/3/userregs/15")

        with self.assertRaises(ValueError):
            self.hdawg.get_user_register(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.get_user_register(4, 0)

        with self.assertRaises(ValueError):
            self.hdawg.get_user_register(0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.get_user_register(0, 16)

    def test_set_user_register(self):
        """Test user register setting."""
        self.hdawg.set_user_register(0, 0, 123)
        self._check_set_value_int("awgs/0/userregs/0", 123)
        self.hdawg.set_user_register(0, 15, -123)
        self._check_set_value_int("awgs/0/userregs/15", -123)
        self.hdawg.set_user_register(3, 0, 123)
        self._check_set_value_int("awgs/3/userregs/0", 123)
        self.hdawg.set_user_register(3, 15, -123)
        self._check_set_value_int("awgs/3/userregs/15", -123)

        with self.assertRaises(ValueError):
            self.hdawg.set_user_register(-1, 0, 456)

        with self.assertRaises(ValueError):
            self.hdawg.set_user_register(4, 0, 456)

        with self.assertRaises(ValueError):
            self.hdawg.set_user_register(0, -1, 789)

        with self.assertRaises(ValueError):
            self.hdawg.set_user_register(0, 16, 789)


if __name__ == '__main__':
    unittest.main()
