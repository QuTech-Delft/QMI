"""Test cases for Zurich Instruments HDAWG."""
import enum
import json
import jsonschema
import logging
import unittest
from unittest.mock import call, Mock, ANY, PropertyMock
import warnings

import numpy as np

from qmi.instruments.zurich_instruments import ZurichInstruments_Hdawg
from qmi.core.exceptions import QMI_InvalidOperationException, QMI_ApplicationException
from tests.patcher import PatcherQmiContext as QMI_Context

_DEVICE_HOST = "localhost"
_DEVICE_PORT = 12345
_DEVICE_NAME = "DEV8888"
_SCHEMA = {"/DEV8888/awgs/0/commandtable/schema": [{"vector": """{
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
}"""}]}


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
        self._awg_module.finished.side_effect = [True, False, False, True]

        self._daq_server = PropertyMock()
        self._daq_server.awgModule = Mock(return_value=self._awg_module)

    def tearDown(self):
        with warnings.catch_warnings():
            # Suppress warnings when instrument not correctly closed.
            warnings.simplefilter("ignore", ResourceWarning)

        logging.getLogger("qmi.core.instrument").setLevel(logging.NOTSET)

    def test_openclose(self):
        """Nominal open/close sequence."""

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.ziDAQServer", return_value=self._daq_server
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.AwgModule", return_value=self._awg_module
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst.core"
            ) as core_patch:
            core_patch.ziDAQServer = Mock(return_value=self._daq_server)
            core_patch.AwgModule = Mock(return_value=self._awg_module)
            self.hdawg = ZurichInstruments_Hdawg(
                self.ctx,
                "HDAWG",
                server_host=_DEVICE_HOST,
                server_port=_DEVICE_PORT,
                device_name=_DEVICE_NAME
            )
            self.hdawg.open()
            self.hdawg.close()

        expected_daq_server_calls = [
            # open()
            call.connectDevice(_DEVICE_NAME, "1GbE"),
            call.awgModule(),
            # close()
            call.disconnect()
        ]
        self.assertEqual(self._daq_server.mock_calls, expected_daq_server_calls)

        expected_awg_module_calls = [
            # open()
            call.set("device", _DEVICE_NAME),
            call.set("index", 0),
            call.finished(),
            call.execute(),
            call.finished(),
            # close()
            call.finished(),
            call.finish(),
            call.finished()
        ]
        self.assertEqual(self._awg_module.mock_calls, expected_awg_module_calls)

    def test_failed_open1(self):
        """Failed open sequence."""
        self._awg_module.finished.side_effect = [False]

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.ziDAQServer", return_value=self._daq_server
        ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.AwgModule", return_value=self._awg_module
        ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst"
        ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst.core"
        ) as core_patch:
            core_patch.ziDAQServer = Mock(return_value=self._daq_server)
            core_patch.AwgModule = Mock(return_value=self._awg_module)
            self.hdawg = ZurichInstruments_Hdawg(
                self.ctx,
                "HDAWG",
                server_host=_DEVICE_HOST,
                server_port=_DEVICE_PORT,
                device_name=_DEVICE_NAME
            )
            with self.assertRaises(AssertionError):
                self.hdawg.open()

        expected_daq_server_calls = [
            call.connectDevice(_DEVICE_NAME, "1GbE"),
            call.awgModule()
        ]
        self.assertEqual(self._daq_server.mock_calls, expected_daq_server_calls)

        expected_awg_module_calls = [
            call.set("device", _DEVICE_NAME),
            call.set("index", 0),
            call.finished()
        ]
        self.assertEqual(self._awg_module.mock_calls, expected_awg_module_calls)

    def test_failed_open2(self):
        """Failed open sequence."""
        self._awg_module.finished.side_effect = [True, True]

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.ziDAQServer", return_value=self._daq_server
        ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.AwgModule", return_value=self._awg_module
        ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst"
        ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst.core"
        ) as core_patch:  # , unittest.mock.patch(
            #     "qmi.instruments.zurich_instruments.hdawg.zhinst.utils"
            # ) as utils_patch:
            core_patch.ziDAQServer = Mock(return_value=self._daq_server)
            core_patch.AwgModule = Mock(return_value=self._awg_module)
            self.hdawg = ZurichInstruments_Hdawg(
                self.ctx,
                "HDAWG",
                server_host=_DEVICE_HOST,
                server_port=_DEVICE_PORT,
                device_name=_DEVICE_NAME
            )
            with self.assertRaises(AssertionError):
                self.hdawg.open()

        expected_daq_server_calls = [
            call.connectDevice(_DEVICE_NAME, "1GbE"),
            call.awgModule()
        ]
        self.assertEqual(self._daq_server.mock_calls, expected_daq_server_calls)

        expected_awg_module_calls = [
            call.set("device", _DEVICE_NAME),
            call.set("index", 0),
            call.finished(),
            call.execute(),
            call.finished()
        ]
        self.assertEqual(self._awg_module.mock_calls, expected_awg_module_calls)

    def test_failed_close1(self):
        """Failed close sequence."""
        self._awg_module.finished.side_effect = [True, False, True]

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.ziDAQServer", return_value=self._daq_server
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.AwgModule", return_value=self._awg_module
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst.core"
            ) as core_patch:
            core_patch.ziDAQServer = Mock(return_value=self._daq_server)
            core_patch.AwgModule = Mock(return_value=self._awg_module)
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

        expected_daq_server_calls = [
            # open()
            call.connectDevice(_DEVICE_NAME, "1GbE"),
            call.awgModule()
        ]
        self.assertEqual(self._daq_server.mock_calls, expected_daq_server_calls)

        expected_awg_module_calls = [
            # open()
            call.set("device", _DEVICE_NAME),
            call.set("index", 0),
            call.finished(),
            call.execute(),
            call.finished(),
            # close()
            call.finished()
        ]
        self.assertEqual(self._awg_module.mock_calls, expected_awg_module_calls)

    def test_failed_close2(self):
        """Failed close sequence."""
        self._awg_module.finished.side_effect = [True, False, False, False]

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.ziDAQServer", return_value=self._daq_server
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.AwgModule", return_value=self._awg_module
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst.core"
            ) as core_patch:
            core_patch.ziDAQServer = Mock(return_value=self._daq_server)
            core_patch.AwgModule = Mock(return_value=self._awg_module)
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

        expected_daq_server_calls = [
            # open()
            call.connectDevice(_DEVICE_NAME, "1GbE"),
            call.awgModule()
        ]
        self.assertEqual(self._daq_server.mock_calls, expected_daq_server_calls)

        expected_awg_module_calls = [
            # open()
            call.set("device", _DEVICE_NAME),
            call.set("index", 0),
            call.finished(),
            call.execute(),
            call.finished(),
            # close()
            call.finished(),
            call.finish(),
            call.finished()
        ]
        self.assertEqual(self._awg_module.mock_calls, expected_awg_module_calls)

    def test_failed_open_notclosed(self):
        """Open device that is already open."""
        self._awg_module.finished.side_effect = [True, False, False, True]
        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.ziDAQServer", return_value=self._daq_server
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.AwgModule", return_value=self._awg_module
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst.core"
            ) as core_patch:
            core_patch.ziDAQServer = Mock(return_value=self._daq_server)
            core_patch.AwgModule = Mock(return_value=self._awg_module)
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
                "qmi.instruments.zurich_instruments.hdawg.ziDAQServer", return_value=self._daq_server
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.AwgModule", return_value=self._awg_module
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst.core"
            ) as core_patch:
            core_patch.ziDAQServer = Mock(return_value=self._daq_server)
            core_patch.AwgModule = Mock(return_value=self._awg_module)
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
        logging.getLogger("qmi.instruments.zurich_instruments.hdawg").setLevel(logging.CRITICAL)

        ctx = QMI_Context("TestHDAWGMethods")
        self._awg_module = PropertyMock()
        self._awg_module.finished.side_effect = [True, False, False, True]
        self._awg_module.getInt = Mock()
        self._awg_module.getDouble = Mock()

        self._daq_server = PropertyMock()
        self._daq_server.awgModule = Mock(return_value=self._awg_module)
        self._daq_server.get = Mock(return_value=_SCHEMA)

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.ziDAQServer", return_value=self._daq_server
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.AwgModule", return_value=self._awg_module
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst.core"
            ) as core_patch:
            core_patch.ziDAQServer = Mock(return_value=self._daq_server)
            core_patch.AwgModule = Mock(return_value=self._awg_module)
            self.hdawg = ZurichInstruments_Hdawg(
                ctx,
                "HDAWG",
                server_host=_DEVICE_HOST,
                server_port=_DEVICE_PORT,
                device_name=_DEVICE_NAME
            )
            self.hdawg.open()

        self._awg_module.reset_mock()
        self._daq_server.reset_mock()

    def _check_get_value_string(self, node_path):
        expected_calls = [
            call.getString("/{}/{}".format(_DEVICE_NAME, node_path))
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def _check_get_value_int(self, node_path):
        expected_calls = [
            call.getInt("/{}/{}".format(_DEVICE_NAME, node_path))
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def _check_get_value_float(self, node_path):
        expected_calls = [
            call.getDouble("/{}/{}".format(_DEVICE_NAME, node_path))
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def _check_set_value(self, node_path, value):
        expected_calls = [
            call.set("/{}/{}".format(_DEVICE_NAME, node_path), value)
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def _check_set_value_int(self, node_path, value):
        expected_calls = [
            call.setInt("/{}/{}".format(_DEVICE_NAME, node_path), value)
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def _check_get_value_double(self, node_path):
        expected_calls = [
            call.getDouble("/{}/{}".format(_DEVICE_NAME, node_path))
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def _check_set_value_double(self, node_path, value):
        expected_calls = [
            call.setDouble("/{}/{}".format(_DEVICE_NAME, node_path), value)
        ]
        self._daq_server.assert_has_calls(expected_calls)

    def tearDown(self):
        self.hdawg.close()
        logging.getLogger("qmi.instruments.zurich_instruments.hdawg").setLevel(logging.NOTSET)

    def test_generic_set(self):
        """Test setter."""
        node = "my/test/node"
        value = "value"
        self.hdawg.set_node_value(node, value)
        self._check_set_value(node, value)

    def test_generic_get_string(self):
        """Test getter."""
        node = "my/test/node"
        value = "value"
        self._daq_server.getString.return_value = value
        result = self.hdawg.get_node_string(node)
        self._check_get_value_string(node)
        self.assertEqual(result, value)

    def test_generic_get_int(self):
        """Test getter."""
        node = "my/test/node"
        value = 123
        self._daq_server.getInt.return_value = value
        result = self.hdawg.get_node_int(node)
        self._check_get_value_int(node)
        self.assertEqual(result, value)

    def test_generic_set_int(self):
        """Test setter."""
        node = "my/test/node"
        value = 123
        self.hdawg.set_node_int(node, value)
        self._check_set_value_int(node, value)

    def test_generic_get_double(self):
        """Test getter."""
        node = "my/test/node"
        value = 123.456
        self._daq_server.getDouble.return_value = value
        result = self.hdawg.get_node_double(node)
        self._check_get_value_double(node)
        self.assertEqual(result, value)

    def test_generic_set_double(self):
        """Test setter."""
        node = "my/test/node"
        value = 123.345
        self.hdawg.set_node_double(node, value)
        self._check_set_value_double(node, value)

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

        self._awg_module.getInt.side_effect = [0, 0]  # successful compilation; upload completed
        self._awg_module.getDouble.side_effect = [1.0]  # upload progress

        expected_calls = [
            call.set("compiler/sourcestring", expected_source),
            call.getInt("compiler/status"),
            call.getDouble("progress"),
            call.getInt("elf/status"),
        ]

        self.hdawg.compile_and_upload(source, replacements)
        self.assertEqual(expected_calls, self._awg_module.mock_calls)
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
                self._awg_module.getInt.side_effect = [0, 0]  # successful compilation; upload completed
                self._awg_module.getDouble.side_effect = [1.0]  # upload progress

                self.hdawg.compile_and_upload(source, replacements)

                self._awg_module.set.assert_called_once_with("compiler/sourcestring", expected_source)
                self.assertTrue(self.hdawg.compilation_successful())
                self._awg_module.set.reset_mock()

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
                self._awg_module.getInt.side_effect = [0, 0]  # successful compilation; upload completed
                self._awg_module.getDouble.side_effect = [1.0]  # upload progress

                self.hdawg.compile_and_upload(source, {"$PAR": value})

                self._awg_module.set.assert_called_once_with("compiler/sourcestring", expected_source)
                self.assertTrue(self.hdawg.compilation_successful())
                self._awg_module.set.reset_mock()

    def test_replacement_value_bad_types(self):
        """Test replacement type."""
        with self.assertRaises(ValueError):
            self.hdawg.compile_and_upload("", {"$PAR": None})  # wrong type

        with self.assertRaises(ValueError):
            self.hdawg.compile_and_upload("", {"$PAR": object()})  # wrong type

    def test_compile_error(self):
        """Test failed compile sequence."""
        source = "while(true) {}"

        self._awg_module.getInt.side_effect = [1]  # failed compilation

        expected_calls = [
            call.set("compiler/sourcestring", source),
            call.getInt("compiler/status"),
            call.getString("compiler/statusstring")
        ]

        self.hdawg.compile_and_upload(source)

        self.assertEqual(expected_calls, self._awg_module.mock_calls)
        self.assertFalse(self.hdawg.compilation_successful())

    def test_compile_timeout(self):
        """Test timed-out compile sequence."""
        source = "while(true) {}"

        self._awg_module.getInt.return_value = -1  # idle

        expected_calls = [
            call.set("compiler/sourcestring", source),
            call.getInt("compiler/status"),
            call.getInt("compiler/status"),
        ]
        self.hdawg.COMPILE_TIMEOUT = 0.1
        self.hdawg.UPLOAD_TIMEOUT = 0.1
        with self.assertRaises(RuntimeError):
            self.hdawg.compile_and_upload(source)

        self.assertEqual(self._awg_module.mock_calls, expected_calls)

    def test_elf_upload_error(self):
        """Test failed ELF upload sequence."""
        source = "while(true) {}"

        self._awg_module.getInt.side_effect = [0, 1]  # successful compilation; upload timed out
        self._awg_module.getDouble.side_effect = [0.3]  # upload progress

        expected_calls = [
            call.set("compiler/sourcestring", source),
            call.getInt("compiler/status"),
            call.getDouble("progress"),
            call.getInt("elf/status"),
        ]

        self.hdawg.compile_and_upload(source)

        self.assertEqual(expected_calls, self._awg_module.mock_calls)
        self.assertFalse(self.hdawg.compilation_successful())

    def test_elf_upload_timeout(self):
        """Test timed-out ELF upload sequence."""
        source = "while(true) {}"

        self._daq_server.getInt.side_effect = [0, -1, -1]  # successful compilation; failed upload
        self._awg_module.getInt.return_value = 0  # = [0, -1, -1]  # successful compilation; upload timed out
        self._awg_module.getDouble.side_effect = [0.0, 0.5]  # upload progress

        expected_calls = [
            call.set("compiler/sourcestring", source),
            call.getInt("compiler/status"),
            # call.getInt("compiler/status"),
            call.getDouble("progress"),
            # call.getInt("elf/status"),
            call.getDouble("progress"),
            # call.getInt("elf/status"),
        ]
        self.hdawg.UPLOAD_TIMEOUT = 0.1

        with self.assertRaises(RuntimeError) as err:
            self.hdawg.compile_and_upload(source)

        self.assertEqual(f"Upload process timed out (timeout={self.hdawg.UPLOAD_TIMEOUT})", str(err.exception))
        self.assertEqual(expected_calls, self._awg_module.mock_calls)

    def test_upload_waveform(self):
        """Test waveform upload."""
        wave1 = [1, 2, 3]
        wave2 = [4, 5, 6]
        markers = [7, 8, 9]

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.zhinst"
            ), unittest.mock.patch(
            "qmi.instruments.zurich_instruments.hdawg.zhinst.utils"
            ) as utils_patch:
            utils_patch.convert_awg_waveform = Mock(return_value="WAVEFORM")
            self.hdawg.upload_waveform(0, 0, wave1, wave2, markers)

        expected_utils_calls = [
            call.convert_awg_waveform(wave1, wave2, markers)
        ]

        expected_daq_server_calls = [
            call.setVector(f"/{_DEVICE_NAME}/awgs/0/waveform/waves/0", "WAVEFORM")
        ]
        self._daq_server.assert_has_calls(expected_daq_server_calls)
        utils_patch.assert_has_calls(expected_utils_calls)

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

        self.hdawg.upload_command_table(0, command_table_entries)

        expected_daq_server_calls = [
            call.setVector(f"/{_DEVICE_NAME}/awgs/0/commandtable/data", ANY)
        ]
        self._daq_server.assert_has_calls(expected_daq_server_calls)

        uploaded_ct = json.loads(self._daq_server.setVector.call_args[0][1])
        self.assertListEqual(uploaded_ct["table"], command_table_entries)

    def test_upload_command_table_invalid_schema(self):
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
        with unittest.mock.patch("qmi.instruments.zurich_instruments.hdawg.json", spec=json) as json_patch:
            json_patch.validate = Mock(side_effect=[ValueError("Invalid schema")])
            with self.assertRaises(ValueError) as verr_2:
                self.hdawg.upload_command_table(0, command_table_entries)

        self.assertEqual("Invalid schema", str(verr_2.exception))

    def test_upload_empty_command_table(self):
        """Test command table upload."""
        table = []
        awg_index = 1
        # Create the command table from the provided entries.
        command_table = {
            "header": {"version":"0.4"}, "table": table
        }
        set_vector = "/{}/awgs/{}/commandtable/data".format(_DEVICE_NAME, awg_index)

        self.hdawg.upload_command_table(awg_index, table)
        self._daq_server.setVector.assert_called_once_with(set_vector, json.dumps(command_table, allow_nan=False).replace(" ", ""))

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
        with self.assertRaises(ValueError) as verr:
            self.hdawg.upload_command_table(0, command_table_entries)

        with unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.json", spec=json
            ) as json_patch, unittest.mock.patch(
                "qmi.instruments.zurich_instruments.hdawg.jsonschema", spec=jsonschema
        ) as schema_patch:
            json_patch.loads = Mock(return_value=json.loads(_SCHEMA["/DEV8888/awgs/0/commandtable/schema"][0]["vector"]))
            json_patch.dumps = Mock(side_effect=[TypeError("Ugly value")])
            schema_patch.validate = Mock()
            with self.assertRaises(ValueError) as verr_2:
                self.hdawg.upload_command_table(0, command_table_entries)

        self.assertEqual("Invalid command table", str(verr.exception))
        self.assertEqual("Invalid value in command table", str(verr_2.exception))

    def test_upload_command_table_wrong_awg(self):
        """Test invalid command table upload."""
        with self.assertRaises(ValueError):
            self.hdawg.upload_command_table(-1, [])

        with self.assertRaises(ValueError):
            self.hdawg.upload_command_table(4, [])

    def test_sync(self):
        """Test sync method."""
        self.hdawg.sync()

        expected_daq_server_calls = [
            call.sync()
        ]
        self.assertEqual(self._daq_server.mock_calls, expected_daq_server_calls)

    def test_set_channel_grouping(self):
        """Test channel grouping setting."""
        self.hdawg.set_channel_grouping(2)
        self._check_set_value_int("system/awg/channelgrouping", 2)

        with self.assertRaises(ValueError):
            self.hdawg.set_channel_grouping(1)

    def test_set_reference_clock_source(self):
        """Test reference clock source setting."""
        self.hdawg.set_reference_clock_source(0)
        self._check_set_value_int("system/clocks/referenceclock/source", 0)
        self.hdawg.set_reference_clock_source(1)
        self._check_set_value_int("system/clocks/referenceclock/source", 1)
        self.hdawg.set_reference_clock_source(2)
        self._check_set_value_int("system/clocks/referenceclock/source", 2)

        with self.assertRaises(ValueError):
            self.hdawg.set_reference_clock_source(3)

    def test_get_reference_clock_status(self):
        """Test reference clock source status."""
        self.hdawg.get_reference_clock_status()
        self._check_get_value_int("system/clocks/referenceclock/status")

    def test_set_sample_clock_frequency(self):
        """"Test sample clock setting."""
        self.hdawg.set_sample_clock_frequency(1234.5e6)
        self._check_set_value_double("system/clocks/sampleclock/freq", 1234.5e6)

    def test_get_sample_clock_status(self):
        """Test reference clock source status."""
        self.hdawg.get_sample_clock_status()
        self._check_get_value_int("system/clocks/sampleclock/status")

    def test_set_trigger_impedance(self):
        """Test trigger impedance setting."""
        self.hdawg.set_trigger_impedance(0, 0)
        self._check_set_value_int("triggers/in/0/imp50", 0)
        self.hdawg.set_trigger_impedance(0, 1)
        self._check_set_value_int("triggers/in/0/imp50", 1)
        self.hdawg.set_trigger_impedance(7, 0)
        self._check_set_value_int("triggers/in/7/imp50", 0)
        self.hdawg.set_trigger_impedance(7, 1)
        self._check_set_value_int("triggers/in/7/imp50", 1)

        with self.assertRaises(ValueError):
            self.hdawg.set_trigger_impedance(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_trigger_impedance(8, 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_trigger_impedance(0, 2)

        with self.assertRaises(ValueError):
            self.hdawg.set_trigger_impedance(8, 2)

    def test_set_trigger_level(self):
        """Test trigger level setting."""
        self.hdawg.set_trigger_level(0, 0.0)
        self._check_set_value_double("triggers/in/0/level", 0.0)
        self.hdawg.set_trigger_level(0, -5.0)
        self._check_set_value_double("triggers/in/0/level", -5.0)
        self.hdawg.set_trigger_level(0, 5.0)
        self._check_set_value_double("triggers/in/0/level", 5.0)
        self.hdawg.set_trigger_level(7, 0.0)
        self._check_set_value_double("triggers/in/7/level", 0.0)
        self.hdawg.set_trigger_level(7, -5.0)
        self._check_set_value_double("triggers/in/7/level", -5.0)
        self.hdawg.set_trigger_level(7, 5.0)
        self._check_set_value_double("triggers/in/7/level", 5.0)

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
        self.hdawg.set_dig_trigger_source(0, 0, 0)
        self._check_set_value_int("awgs/0/auxtriggers/0/channel", 0)
        self.hdawg.set_dig_trigger_source(3, 0, 0)
        self._check_set_value_int("awgs/3/auxtriggers/0/channel", 0)
        self.hdawg.set_dig_trigger_source(0, 1, 0)
        self._check_set_value_int("awgs/0/auxtriggers/1/channel", 0)
        self.hdawg.set_dig_trigger_source(0, 0, 7)
        self._check_set_value_int("awgs/0/auxtriggers/0/channel", 7)

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
        self.hdawg.set_dig_trigger_slope(0, 0, 0)
        self._check_set_value_int("awgs/0/auxtriggers/0/slope", 0)
        self.hdawg.set_dig_trigger_slope(3, 0, 0)
        self._check_set_value_int("awgs/3/auxtriggers/0/slope", 0)
        self.hdawg.set_dig_trigger_slope(0, 1, 0)
        self._check_set_value_int("awgs/0/auxtriggers/1/slope", 0)
        self.hdawg.set_dig_trigger_slope(0, 0, 3)
        self._check_set_value_int("awgs/0/auxtriggers/0/slope", 3)

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

    def test_set_output_amplitude(self):
        """Test output amplitude setting."""
        self.hdawg.set_output_amplitude(0, 0, 1.0)
        self._check_set_value_double("awgs/0/outputs/0/amplitude", 1.0)
        self.hdawg.set_output_amplitude(0, 1, 1.0)
        self._check_set_value_double("awgs/0/outputs/1/amplitude", 1.0)
        self.hdawg.set_output_amplitude(0, 0, -1.0)
        self._check_set_value_double("awgs/0/outputs/0/amplitude", -1.0)
        self.hdawg.set_output_amplitude(0, 1, -1.0)
        self._check_set_value_double("awgs/0/outputs/1/amplitude", -1.0)
        self.hdawg.set_output_amplitude(3, 0, 1.0)
        self._check_set_value_double("awgs/3/outputs/0/amplitude", 1.0)
        self.hdawg.set_output_amplitude(3, 1, 1.0)
        self._check_set_value_double("awgs/3/outputs/1/amplitude", 1.0)
        self.hdawg.set_output_amplitude(3, 0, -1.0)
        self._check_set_value_double("awgs/3/outputs/0/amplitude", -1.0)
        self.hdawg.set_output_amplitude(3, 1, -1.0)
        self._check_set_value_double("awgs/3/outputs/1/amplitude", -1.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_amplitude(-1, 0, 1.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_amplitude(4, 0, 1.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_amplitude(0, -1, 1.0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_amplitude(0, 3, 1.0)

    def test_get_output_amplitude(self):
        """Test output amplitude query."""
        self.hdawg.get_output_amplitude(0, 0)
        self._check_get_value_double("awgs/0/outputs/0/amplitude")
        self.hdawg.get_output_amplitude(0, 1)
        self._check_get_value_double("awgs/0/outputs/1/amplitude")
        self.hdawg.get_output_amplitude(0, 0)
        self._check_get_value_double("awgs/0/outputs/0/amplitude")
        self.hdawg.get_output_amplitude(0, 1)
        self._check_get_value_double("awgs/0/outputs/1/amplitude")
        self.hdawg.get_output_amplitude(3, 0)
        self._check_get_value_double("awgs/3/outputs/0/amplitude")
        self.hdawg.get_output_amplitude(3, 1)
        self._check_get_value_double("awgs/3/outputs/1/amplitude")
        self.hdawg.get_output_amplitude(3, 0)
        self._check_get_value_double("awgs/3/outputs/0/amplitude")
        self.hdawg.get_output_amplitude(3, 1)
        self._check_get_value_double("awgs/3/outputs/1/amplitude")

        with self.assertRaises(ValueError):
            self.hdawg.get_output_amplitude(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.get_output_amplitude(4, 0)

        with self.assertRaises(ValueError):
            self.hdawg.get_output_amplitude(0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.get_output_amplitude(0, 3)

    def test_set_output_channel_hold(self):
        """Test output hold setting."""
        self.hdawg.set_output_channel_hold(0, 0, 1)
        self._check_set_value_int("awgs/0/outputs/0/hold", 1)
        self.hdawg.set_output_channel_hold(0, 1, 1)
        self._check_set_value_int("awgs/0/outputs/1/hold", 1)
        self.hdawg.set_output_channel_hold(0, 0, 1)
        self._check_set_value_int("awgs/0/outputs/0/hold", 1)
        self.hdawg.set_output_channel_hold(0, 1, 1)
        self._check_set_value_int("awgs/0/outputs/1/hold", 1)
        self.hdawg.set_output_channel_hold(3, 0, 1)
        self._check_set_value_int("awgs/3/outputs/0/hold", 1)
        self.hdawg.set_output_channel_hold(3, 1, 1)
        self._check_set_value_int("awgs/3/outputs/1/hold", 1)
        self.hdawg.set_output_channel_hold(3, 0, 1)
        self._check_set_value_int("awgs/3/outputs/0/hold", 1)
        self.hdawg.set_output_channel_hold(3, 1, 1)
        self._check_set_value_int("awgs/3/outputs/1/hold", 1)
        self.hdawg.set_output_channel_hold(0, 0, 0)
        self._check_set_value_int("awgs/0/outputs/0/hold", 0)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_hold(-1, 0, 1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_hold(4, 0, 1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_hold(0, -1, 1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_hold(0, 3, 1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_hold(0, 0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.set_output_channel_hold(0, 0, 2)

    def test_get_output_channel_hold(self):
        """Test output hold query."""
        self.hdawg.get_output_channel_hold(0, 0)
        self._check_get_value_int("awgs/0/outputs/0/hold")
        self.hdawg.get_output_channel_hold(0, 1)
        self._check_get_value_int("awgs/0/outputs/1/hold")
        self.hdawg.get_output_channel_hold(3, 0)
        self._check_get_value_int("awgs/3/outputs/0/hold")
        self.hdawg.get_output_channel_hold(3, 1)
        self._check_get_value_int("awgs/3/outputs/1/hold")

        with self.assertRaises(ValueError):
            self.hdawg.get_output_channel_hold(-1, 0)

        with self.assertRaises(ValueError):
            self.hdawg.get_output_channel_hold(4, 0)

        with self.assertRaises(ValueError):
            self.hdawg.get_output_channel_hold(0, -1)

        with self.assertRaises(ValueError):
            self.hdawg.get_output_channel_hold(0, 3)

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
        self.hdawg.set_output_channel_range(0, 0.0)
        self._check_set_value_double("sigouts/0/range", 0.0)
        self.hdawg.set_output_channel_range(0, 5.0)
        self._check_set_value_double("sigouts/0/range", 5.0)
        self.hdawg.set_output_channel_range(7, 0.0)
        self._check_set_value_double("sigouts/7/range", 0.0)
        self.hdawg.set_output_channel_range(7, 5.0)
        self._check_set_value_double("sigouts/7/range", 5.0)

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

    def test_set_dio_mode(self):
        """Test DIO mode setting."""
        for i in range(4):
            self.hdawg.set_dio_mode(i)
            self._check_set_value_int("dios/0/mode", i)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_mode(-1)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_mode(4)

    def test_set_dio_drive(self):
        """Test DIO drive setting."""
        for i in range(16):
            self.hdawg.set_dio_drive(i)
            self._check_set_value_int("dios/0/drive", i)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_drive(-1)

        with self.assertRaises(ValueError):
            self.hdawg.set_dio_drive(16)

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

    def test_awg_module_enabled(self):
        """Test AWG enable on/off."""
        self.hdawg.get_awg_module_enabled(0)
        self._check_get_value_int("awgs/0/enable")
        self.hdawg.get_awg_module_enabled(3)
        self._check_get_value_int("awgs/3/enable")

        with self.assertRaises(ValueError):
            self.hdawg.get_awg_module_enabled(-1)

        with self.assertRaises(ValueError):
            self.hdawg.get_awg_module_enabled(4)

        self.hdawg.set_awg_module_enabled(0)
        self.hdawg.set_awg_module_enabled(1)

        expected_awg_module_calls = [
            call.set("awg/enable", 0),
            call.set("awg/enable", 1)
        ]
        self.assertEqual(expected_awg_module_calls, self._awg_module.mock_calls)

        with self.assertRaises(ValueError):
            self.hdawg.set_awg_module_enabled(-1)

        with self.assertRaises(ValueError):
            self.hdawg.set_awg_module_enabled(2)


if __name__ == '__main__':
    unittest.main()
