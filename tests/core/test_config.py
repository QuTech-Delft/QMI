#! /usr/bin/env python3

"""Test configuration file processing."""

import unittest
import json
import os
import tempfile

import qmi.core.config
import qmi.core.exceptions


CONFIG_BASIC = """# TEST FILE FOR CONFIG PARSING
{
    "name": "config",
    "num": 13,
    "pi": 3.1415, # this is an approximation
    "nocomment": "the # sign is not special inside strings",
    "comment": #" but this is a comment",
        "and this is the value",
    #"skipped": 18,
    "#": "pound"
}"""

CONFIG_DUPLICATE = """# TEST FILE FOR CONFIG PARSING
{
    "name": "config",
    "num": 13,
    "pi": 3.1415, # this is an approximation
    "nocomment": "the # sign is not special inside strings",
    "comment": #" but this is a comment",
        "and this is the value",
    "pi": 3.1415, # this is a duplicate
    #"skipped": 18,
    "#": "pound"
}"""

PARSED_BASIC = {
    "name": "config",
    "num": 13,
    "pi": 3.1415,
    "nocomment": "the # sign is not special inside strings",
    "comment": "and this is the value",
    "#": "pound"
}

CONFIG_TRICKY = r"""{#}
    "nocomment1": "\"#\"",
    "nocomment2": "\\#",
    "nocomment3": "\\\"#",
    "comment1": "\\",#",
    "comment2": "\u00c0\n"#',
  , "comment3":# "\uuuuu",
        1,
    "comment4"#: "fake",
        :"real",
    "comment5": 5#.0
  , "comment6": [#]
        6, "6"],
    "comment7": #null,
        7,
    "comment8": true#false,
        ,
    "comment9": {#},
        },
    "comment10": { "name"#} : "fake",
        :#"fake" }
"value"##,
}#}}
,
#   "commentX":
    "#nocomment4": 4,
    "nocomment5#": 5,
    "nocomment6":"#6",
    "nocomment7": "7#"#,
  ,#null
    "nocomment8\"#": 333,
# "#" \# \# \#
    "array": [[]#],
        ],
    "null": null
#}}}
}#
"""

PARSED_TRICKY = {
    "nocomment1": '"#"',
    "nocomment2": "\\#",
    "nocomment3": '\\"#',
    "comment1": "\\",
    "comment2": "\xc0\n",
    "comment3": 1,
    "comment4": "real",
    "comment5": 5,
    "comment6": [6, "6"],
    "comment7": 7,
    "comment8": True,
    "comment9": {},
    "comment10": { "name": "value" },
    "#nocomment4": 4,
    "nocomment5#": 5,
    "nocomment6": "#6",
    "nocomment7": "7#",
    'nocomment8"#': 333,
    "array": [[]],
    "null": None
}

# Invalid config: Bad JSON string.
CONFIG_BAD_JSON = """{ "bad": False }"""

# Invalid config: top-level type must be a map.
CONFIG_BAD_TYPE = """[ 3, 4, 5 ]"""


class TestConfigLoad(unittest.TestCase):

    def test_basic(self):
        cfg = qmi.core.config.load_config_string(CONFIG_BASIC)
        self.assertEqual(cfg, PARSED_BASIC)

    def test_tricky(self):
        cfg = qmi.core.config.load_config_string(CONFIG_TRICKY)
        self.assertEqual(cfg, PARSED_TRICKY)

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            cfg = qmi.core.config.load_config_string(CONFIG_DUPLICATE)

    def test_bad_json(self):
        with self.assertRaises(json.JSONDecodeError):
            cfg = qmi.core.config.load_config_string(CONFIG_BAD_JSON)

    def test_bad_type(self):
        with self.assertRaises(qmi.core.exceptions.QMI_ConfigurationException):
            cfg = qmi.core.config.load_config_string(CONFIG_BAD_TYPE)

    def test_file(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            filename = os.path.join(tmpdirname, "test_load_basic.cfg")
            with open(filename, "w") as f:
                f.write(CONFIG_BASIC)
            cfg = qmi.core.config.load_config_file(filename)
        self.assertEqual(cfg, PARSED_BASIC)


class TestConfigDump(unittest.TestCase):

    def test_basic(self):
        s = qmi.core.config.dump_config_string(PARSED_BASIC)
        cfg = json.loads(s)
        self.assertEqual(cfg, PARSED_BASIC)

    def test_tricky(self):
        s = qmi.core.config.dump_config_string(PARSED_TRICKY)
        cfg = json.loads(s)
        self.assertEqual(cfg, PARSED_TRICKY)

    def test_file(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            filename = os.path.join(tmpdirname, "test_dump_basic.cfg")
            qmi.core.config.dump_config_file(PARSED_BASIC, filename)
            with open(filename, "r") as f:
                s = f.read()
        cfg = json.loads(s)
        self.assertEqual(cfg, PARSED_BASIC)

    def test_file_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdirname:
            filename = os.path.join(tmpdirname, "test_dump_overwrite.cfg")
            with open(filename, "w") as f:
                f.write("dummy")
            qmi.core.config.dump_config_file(PARSED_BASIC, filename)
            with open(filename, "r") as f:
                s = f.read()
        cfg = json.loads(s)
        self.assertEqual(cfg, PARSED_BASIC)


if __name__ == "__main__":
    unittest.main()
