#!/usr/bin/env python3

"""Unit tests for qmi.core.config_struct."""

import unittest
from dataclasses import field
from typing import Any

from qmi.core.config_struct import configstruct, config_struct_from_dict, config_struct_to_dict
from qmi.core.exceptions import QMI_ConfigurationException


class TestConfigStruct(unittest.TestCase):

    def test_01_parse_simple(self):
        """Test parsing a simple structure."""

        @configstruct
        class MyConfig:
            i:  int
            s:  str
            f:  float
            b:  bool

        data1 = {
            "i": 42,
            "s": "hello",
            "f": 3.1415,
            "b": False
        }

        data2 = {
            "i": -1,
            "s": "",
            "f": 1.0,
            "b": True
        }

        cfg1 = config_struct_from_dict(data1, MyConfig)
        cfg2 = config_struct_from_dict(data2, MyConfig)

        self.assertIsInstance(cfg1, MyConfig)
        self.assertIsInstance(cfg1.i, int)
        self.assertIsInstance(cfg1.s, str)
        self.assertIsInstance(cfg1.f, float)
        self.assertIsInstance(cfg1.b, bool)
        self.assertEqual(cfg1.i, 42)
        self.assertEqual(cfg1.s, "hello")
        self.assertEqual(cfg1.f, 3.1415)
        self.assertEqual(cfg1.b, False)

        self.assertIsInstance(cfg2, MyConfig)
        self.assertIsInstance(cfg2.i, int)
        self.assertIsInstance(cfg2.s, str)
        self.assertIsInstance(cfg2.f, float)
        self.assertIsInstance(cfg2.b, bool)
        self.assertEqual(cfg2.i, -1)
        self.assertEqual(cfg2.s, "")
        self.assertEqual(cfg2.f, 1.0)
        self.assertEqual(cfg2.b, True)

    def test_02_serialize_simple(self):
        """Test serializing a simple structure."""

        @configstruct
        class MyConfig:
            i:  int
            s:  str
            f:  float
            b:  bool

        cfg1 = MyConfig(i=11, s="sss", f=2.71, b=True)
        data1 = {"i": 11, "s": "sss", "f": 2.71, "b": True}

        q1 = config_struct_to_dict(cfg1)
        self.assertIsInstance(data1, dict)
        self.assertEqual(q1, data1)

    def test_03_float_conversion(self):
        """Test automatic promotion from int to float."""

        @configstruct
        class MyConfig:
            i:  int
            f:  float

        data1 = {"i": 5, "f": 3.0}
        data2 = {"i": 10, "f": -8}

        cfg1 = config_struct_from_dict(data1, MyConfig)
        self.assertIsInstance(cfg1.f, float)
        self.assertEqual(cfg1, MyConfig(i=5, f=3.0))

        cfg2 = config_struct_from_dict(data2, MyConfig)
        self.assertIsInstance(cfg2.f, float)
        self.assertEqual(cfg2, MyConfig(i=10, f=-8.0))

        q1 = config_struct_to_dict(cfg1)
        self.assertEqual(q1, data1)

        q2 = config_struct_to_dict(cfg2)
        self.assertIsInstance(q2["f"], float)
        self.assertEqual(q2, data2)

    def test_04_class_not_dataclass(self):
        """The configuration class must be a dataclass"""
        class MyConfig:
            i:  int
            f:  float

        data1 = {"i": 5, "f": 3.0, "3": "str"}

        exp_error = "Configuration class type must be a dataclass"
        exp_error2 = "Configuration data must be a dataclass instance"
        with self.assertRaises(TypeError) as type_err:
            config_struct_from_dict(data1, MyConfig)

        with self.assertRaises(TypeError) as type_err2:
            config_struct_to_dict(MyConfig)

        self.assertEqual(exp_error, str(type_err.exception))
        self.assertEqual(exp_error2, str(type_err2.exception))

    def test_05_no_keyword_arguments_allowed(self):
        """The configstruct doesn't allow keyword arguments"""
        @configstruct
        class MyConfig:
            i:  int
            f:  float

        exp_error = "config_struct_from_dict() got an unexpected keyword argument 'kwarg'"
        data1 = {"i": 5, "f": 3.0}

        with self.assertRaises(TypeError) as kw_err:
            config_struct_from_dict(data1, MyConfig, kwarg=None)

        self.assertEqual(exp_error, str(kw_err.exception))

    def test_06_unsupported_config_type(self):
        """configstruct dictionary inputs allow only dictionaries with keys as strings."""
        @configstruct
        class MyConfig:
            d:  dict[str, int]

        dict1 = {"d": {"0": 5, 1: 3.0}}
        exp_error = "Unsupported non-string dictionary key 1 in configuration item d"
        with self.assertRaises(QMI_ConfigurationException) as k_err:
            config_struct_from_dict(dict1, MyConfig)

        self.assertEqual(exp_error, str(k_err.exception))

    def test_07_missing_dataclass_input(self):
        """Call to get config_struct_from_dict errors when the respective class is 'forgotten' from inputs."""
        exp_error = "config_struct_from_dict() missing 1 required positional argument: 'cls'"
        with self.assertRaises(TypeError) as kw_err:
            config_struct_from_dict({})

        self.assertEqual(exp_error, str(kw_err.exception))

    def test_08_init_missing_argument(self):
        """The configstruct misses an argument"""
        class MyConfig:
            d:  dict[str, int]

        exp_error = "MyConfig.__init__() missing required argument 'd'"
        cs = configstruct(MyConfig)
        with self.assertRaises(TypeError) as miss_err:
            cs()

        self.assertEqual(exp_error, str(miss_err.exception))

    def test_09_unsupported_value_type_inner(self):
        """Unsupported value type in _inner_config_struct_to_dict excepts."""
        @configstruct
        class MyConfig:
            i:  int

        exp_error = "Unsupported value type: b'5'"

        data1 = {"i": 5}
        cfg1 = config_struct_from_dict(data1, MyConfig)
        cfg1.i = b"5"  # Overwrite the value with an unsupported type
        with self.assertRaises(TypeError) as type_err:
            config_struct_to_dict(cfg1)

        self.assertEqual(exp_error, str(type_err.exception))

    def test_10_unsupported_data_type_in_config(self):
        """Unsupported data type in configstruct excepts (expecting tuple, got list)."""
        @configstruct
        class MyConfig:
            t:  tuple

        exp_error = "Type mismatch in configuration item t: got <class 'list'> while expecting <class 'tuple'>"

        data1 = {"t": [5,]}
        with self.assertRaises(QMI_ConfigurationException) as cfg_err:
            config_struct_from_dict(data1, MyConfig)

        self.assertEqual(exp_error, str(cfg_err.exception))

    def test_11_default_values(self):
        """Test a structure with default values for some fields."""

        @configstruct
        class MyConfig:
            a:  int
            b:  int = 111
            c:  str = "hello"
            d:  bool = True

        data1 = {"a": 1, "b": 2, "c": "howdie", "d": False}
        data2 = {"a": 5}
        data3 = {"a": 6, "c": "", "d": True}

        cfg1 = config_struct_from_dict(data1, MyConfig)
        self.assertEqual(cfg1.a, 1)
        self.assertEqual(cfg1.b, 2)
        self.assertEqual(cfg1.c, "howdie")
        self.assertEqual(cfg1.d, False)

        cfg2 = config_struct_from_dict(data2, MyConfig)
        self.assertEqual(cfg2.a, 5)
        self.assertEqual(cfg2.b, 111)
        self.assertEqual(cfg2.c, "hello")
        self.assertEqual(cfg2.d, True)

        cfg3 = config_struct_from_dict(data3, MyConfig)
        self.assertEqual(cfg3.a, 6)
        self.assertEqual(cfg3.b, 111)
        self.assertEqual(cfg3.c, "")
        self.assertEqual(cfg3.d, True)

        q1 = config_struct_to_dict(cfg1)
        self.assertEqual(q1, data1)

        q2 = config_struct_to_dict(cfg2)
        self.assertEqual(q2, {"a": 5, "b": 111, "c": "hello", "d": True})

        q3 = config_struct_to_dict(cfg3)
        self.assertEqual(q3, {"a": 6, "b": 111, "c": "", "d": True})

    def test_12_default_before_required(self):
        """Test a structure with default fields before required fields."""

        @configstruct
        class MyConfig:
            a:  int = 25
            b:  str

        data1 = {"a": 100, "b": "hello"}
        data2 = {"b": "bye"}

        cfg1 = config_struct_from_dict(data1, MyConfig)
        self.assertEqual(cfg1, MyConfig(a=100, b="hello"))

        cfg2 = config_struct_from_dict(data2, MyConfig)
        self.assertEqual(cfg2, MyConfig(a=25, b="bye"))

    def test_13_advanced_types(self):
        """Test a structure with non-scalar field types."""

        @configstruct
        class MyConfig:
            v:  list
            d:  dict
            vs: list[str]
            di: dict[str, int]
            t:  tuple[int, str]
            a:  Any
            opt: int | None

        data1 = {
            "v": [101, 102, 103],
            "d": {"a": "aap", "n": "noot"},
            "vs": ["one", "two"],
            "di": {"one": 1, "thousand": 1000},
            "t": [5, "qqq"],
            "a": [15],
            "opt": 25
        }

        cfg1 = config_struct_from_dict(data1, MyConfig)
        self.assertEqual(cfg1, MyConfig(
            v=[101, 102, 103],
            d={"a": "aap", "n": "noot"},
            vs=["one", "two"],
            di={"one": 1, "thousand": 1000},
            t=(5, "qqq"),
            a=[15],
            opt=25))

        q1 = config_struct_to_dict(cfg1)

        self.assertEqual(q1, data1)

    def test_14_advanced_defaults(self):
        """Test a structure with default values for non-scalar fields."""

        @configstruct
        class MyConfig:
            v:  list            = field(default_factory=list)
            d:  dict            = field(default_factory=dict)
            vs: list[str]       = field(default_factory=list)
            di: dict[str, int]  = field(default_factory=dict)
            t:  tuple[int, str] = (0, "")
            a:  Any             = False
            opt: int | None  = None

        data1 = {
            "v": [101, 102, 103],
            "d": {"a": "aap", "n": "noot"}
        }

        data2 = {
            "vs": ["one", "two"],
            "di": {"one": 1, "thousand": 1000},
            "t": [5, "qqq"],
            "a": [15],
            "opt": 25
        }

        cfg1 = config_struct_from_dict(data1, MyConfig)
        self.assertEqual(cfg1, MyConfig(
            v=[101, 102, 103],
            d={"a": "aap", "n": "noot"},
            vs=[],
            di={},
            t=(0, ""),
            a=False,
            opt=None))

        cfg2 = config_struct_from_dict(data2, MyConfig)
        self.assertEqual(cfg2, MyConfig(
            vs=["one", "two"],
            di={"one": 1, "thousand": 1000},
            t=(5, "qqq"),
            a=[15],
            opt=25))

        q1 = config_struct_to_dict(cfg1)
        self.assertEqual(q1, {
            "v": [101, 102, 103],
            "d": {"a": "aap", "n": "noot"},
            "vs": [],
            "di": {},
            "t": [0, ""],
            "a": False,
            "opt": None
        })

        q2 = config_struct_to_dict(cfg2)
        self.assertEqual(q2, {
            "v": [],
            "d": {},
            "vs": ["one", "two"],
            "di": {"one": 1, "thousand": 1000},
            "t": [5, "qqq"],
            "a": [15],
            "opt": 25
        })

    def test_15_nested_types(self):
        """Test a structure with default values for non-scalar fields."""

        @configstruct
        class MyConfig:
            vvi: list[list[int]]
            dvs: dict[str, list[str]]
            optv: list[float] | None = None

        data1 = {
            "vvi": [[], [1], [2, 3]],
            "dvs": {"one": ["1"], "two": ["00", "11"]},
            "optv": None
        }

        data2 = {
            "vvi": [[], [0, 0, 0], []],
            "dvs": {},
            "optv": [3.14, 1.4142]
        }

        cfg1 = config_struct_from_dict(data1, MyConfig)
        self.assertEqual(cfg1, MyConfig(
            vvi=[[], [1], [2, 3]],
            dvs={"one": ["1"], "two": ["00", "11"]},
            optv=None))

        cfg2 = config_struct_from_dict(data2, MyConfig)
        self.assertEqual(cfg2, MyConfig(
            vvi=[[], [0, 0, 0], []],
            dvs={},
            optv=[3.14, 1.4142]))

        q1 = config_struct_to_dict(cfg1)
        self.assertEqual(q1, data1)

        q2 = config_struct_to_dict(cfg2)
        self.assertEqual(q2, data2)

    def test_16_tuple_t_dotdotdot(self):
        """Test a tuple[T, ...] structure field type."""

        @configstruct
        class MyConfig:
            t:  tuple[int, ...]

        data1 = {
            "t": [5, 4, 3, 2, 1],
            }

        cfg1 = config_struct_from_dict(data1, MyConfig)
        self.assertEqual(cfg1, MyConfig(t=(5, 4, 3, 2, 1),))

        q1 = config_struct_to_dict(cfg1)

        self.assertEqual(q1, data1)

    def test_17_typing_types(self):
        """Test a structure with unspecified Typing field types."""

        @configstruct
        class MyConfig:
            vs: list
            di: dict
            t: tuple

        data1 = {
            "vs": ["one", "two"],
            "di": {"one": 1, "thousand": 1000},
            "t": (5, "qqq"),
        }

        cfg1 = config_struct_from_dict(data1, MyConfig)
        self.assertEqual(cfg1, MyConfig(
            vs=["one", "two"],
            di={"one": 1, "thousand": 1000},
            t=(5, "qqq"),
        ))

        # NOTE: When transforming back to dict, tuple(s) are turned to list(s) in _dictify_list_value.
        q1 = config_struct_to_dict(cfg1)
        data1.update({"t": [5, "qqq"]})
        self.assertEqual(q1, data1)

    def test_21_sub_structs(self):
        """Test a structure with sub-structures."""

        @configstruct
        class MySub:
            x: int
            y: float

        @configstruct
        class MyConfig:
            s: MySub
            v: list[MySub]

        data1 = {
            "s": {"x": 100, "y": 3.1415},
            "v": [
                {"x": 101, "y": 1.0},
                {"x": 102, "y": -1.0e6}
            ]
        }

        cfg1 = config_struct_from_dict(data1, MyConfig)
        self.assertIsInstance(cfg1, MyConfig)
        self.assertIsInstance(cfg1.s, MySub)
        self.assertIsInstance(cfg1.v[0], MySub)
        self.assertEqual(cfg1.s, MySub(x=100, y=3.1415))
        self.assertEqual(cfg1.v, [MySub(x=101, y=1.0),
                                  MySub(x=102, y=-1.0e6)])

    def test_22_extended_structs(self):
        """Test extended structure types."""

        @configstruct
        class MySubBase:
            x: int

        @configstruct
        class MySubExt(MySubBase):
            y: float

        @configstruct
        class MyBase:
            i: int
            s: str
            d: MySubBase

        @configstruct
        class MyConfig(MyBase):
            f: float
            s: str = "default"
            d: MySubExt

        data1 = {
            "i": 21,
            "f": 1.234,
            "s": "hello",
            "d": {"x": 10, "y": 3.14}
        }

        data2 = {
            "i": 50,
            "f": 123.4,
            "d": {"x": 11, "y": 1.111}
        }

        cfg1 = config_struct_from_dict(data1, MyConfig)
        self.assertEqual(cfg1, MyConfig(i=21, f=1.234, s="hello", d=MySubExt(x=10, y=3.14)))

        cfg2 = config_struct_from_dict(data2, MyConfig)
        self.assertEqual(cfg2, MyConfig(i=50, f=123.4, s="default", d=MySubExt(x=11, y=1.111)))

        q1 = config_struct_to_dict(cfg1)
        self.assertEqual(q1, data1)

        q2 = config_struct_to_dict(cfg2)
        self.assertEqual(q2, {
            "i": 50,
            "f": 123.4,
            "s": "default",
            "d": {"x": 11, "y": 1.111}
        })

    def test_31_fail_missing_field(self):
        """Fail on missing field."""

        @configstruct
        class MySub:
            p: int

        @configstruct
        class MyConfig:
            x: int
            y: float | None  # NOTE : this field is not optional because it has no default
            d: MySub

        data1 = {}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data1, MyConfig)

        data2 = {"x": 25, "d": {"p": 1}}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data2, MyConfig)

        data3 = {"y": 1.0, "d": {"p": 1}}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data3, MyConfig)

        data4 = {"x": 25, "y": 1.0}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data4, MyConfig)

        data5 = {"x": 25, "y": 1.0, "d": {}}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data5, MyConfig)

    def test_32_fail_unknown_field(self):
        """Fail on unknown field name."""

        @configstruct
        class MySub:
            p: int

        @configstruct
        class MyConfig:
            x: int
            d: MySub

        data1 = {"x": 21, "d": {"p": 100}, "yy": 22}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data1, MyConfig)

        data2 = {"x": 21, "d": {"p": 100, "qq": 101}}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data2, MyConfig)

    def test_33_fail_bad_type(self):
        """Fail on incorrect value for field type."""

        @configstruct
        class MySub:
            b: bool

        @configstruct
        class MyConfig:
            v: list[int]
            s: str
            d: MySub
            m: dict[str, int] = field(default_factory=dict)

        data1 = {"v": 5, "s": "hello", "d": {"b": False}}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data1, MyConfig)

        data2 = {"v": [5], "s": 0, "d": {"b": False}}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data2, MyConfig)

        data3 = {"v": [5], "s": "hello", "d": {"b": 0}}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data3, MyConfig)

        data4 = {"v": [5, "6"], "s": "hello", "d": {"b": False}}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data4, MyConfig)

        data5 = {"v": [], "s": "hello", "d": {"b": False}, "m": {"a": "b"}}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data5, MyConfig)

    def test_34_fail_unsupported_type(self):
        """Fail on unsupported field type in struct definition."""

        @configstruct
        class MyConfig1:
            x: list | tuple  # union not supported

        data1 = {"x": []}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data1, MyConfig1)

        @configstruct
        class MyConfig2:
            x: dict[int, int]  # integer dict key not supported

        data2 = {"x": {}}
        with self.assertRaises(QMI_ConfigurationException):
            config_struct_from_dict(data2, MyConfig2)

    def test_41_direct_instantiation_simple(self):
        """Test direct instantiation of a configstruct object."""

        @configstruct
        class MyConfig:
            x: int
            y: str

        x_val = 5
        y_val = "hello"
        my_config = MyConfig(x=x_val, y=y_val)

        self.assertEqual(my_config.x, x_val)
        self.assertEqual(my_config.y, y_val)

    def test_42_direct_instantiation_complex(self):
        """Test direct instantiation of a nested configstruct object."""

        @configstruct
        class MyConfig1:
            x: int
            y: str

        @configstruct
        class MyConfig2:
            v: MyConfig1
            w: dict[str, MyConfig1]

        x_val1 = 1
        x_val2 = 2
        y_val1 = "hello"
        y_val2 = "world"
        my_config = MyConfig2(
            v=MyConfig1(x=x_val1, y=y_val1),
            w={"data": MyConfig1(x=x_val2, y=y_val2)}
        )

        self.assertEqual(my_config.v.x, x_val1)
        self.assertEqual(my_config.v.y, y_val1)
        self.assertEqual(my_config.w["data"].x, x_val2)
        self.assertEqual(my_config.w["data"].y, y_val2)

    def test_43_direct_instantiation_optional(self):
        """Test direct instantiation with optional fields."""

        @configstruct
        class MyConfig:
            x: int
            y: str | None = None

        x_val = 3
        my_config = MyConfig(x=x_val)

        self.assertEqual(my_config.x, x_val)
        self.assertIsNone(my_config.y)

    def test_51_fail_direct_instantiation_wrong_type(self):
        """Fail on wrong field type."""

        @configstruct
        class MyConfig:
            x: int
            y: str

        with self.assertRaises(QMI_ConfigurationException):
            MyConfig(x=1, y=2)

    def test_52_fail_direct_instantiation_missing_field(self):
        """Fail on missing field."""

        @configstruct
        class MyConfig:
            x: int
            y: str

        with self.assertRaises(TypeError):
            MyConfig(x=1)


if __name__ == "__main__":
    unittest.main()
