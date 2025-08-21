"""Routines for structured configuration data.

This module provides functions for loading configuration data into
a tree structure of Python data classes.
This provides two advantages:

 1. The configuration file is validated and type-checked against
    the expected structure immediately when the file is loaded.
 2. The configuration data can be accessed through attributes of well-typed
    data classes instead of through dictionary lookups.

The structure of the configuration data is defined as a set of data classes.
Each structure is defined using the ``@configstruct`` decorator.

Only the following data types are allowed for fields of configuration structures:

 - ``int``, ``float``, ``str``, ``bool``
 - another configuration structure type;
 - ``list[T]`` where `T` is a supported field type
 - ``dict[str, T]`` where `T` is a supported field type
 - ``tuple[T1, T2, T3]`` or ``tuple[T, ...]`` where `T`, `T1`, etc are supported field types
 - ``Optional[T]`` where `T` is a supported field type
 - ``Any``

A default value may be specified in the data class definition.
The default value, if present, will be used when the field is not present
in the configuration data. Fields without default value are mandatory.

Existing structure definitions may be extended (for example at application
level). This is done by subclassing the existing definition and adding
more fields.
"""

import collections
import dataclasses

from typing import Any, TypeVar

from qmi.core.exceptions import QMI_ConfigurationException

_T = TypeVar("_T")
_StrDict = dict[str, Any]


def configstruct(cls: type[_T]) -> type[_T]:
    """Class decorator to mark classes that hold QMI configuration data.

    This decorator is based on the standard `@dataclass` decorator.
    It calls ``@dataclass(init=False)`` to do most of the work,
    then adds a custom `__init__()` method.
    """

    # New __init__() function for the class.
    def initfn(self: Any, **kwargs: Any) -> None:

        # Walk the list of field definitions.
        for f in dataclasses.fields(cls):  # type: ignore
            if f.init and f.name in kwargs:
                # Value specified as argument to __init__().
                value = kwargs.pop(f.name)
                _parse_config_value(value, f.type, [])
                setattr(self, f.name, value)
            elif f.default is not dataclasses.MISSING:
                # No value specified; use default value of field.
                setattr(self, f.name, f.default)
            elif f.default_factory is not dataclasses.MISSING:
                # No value specified; use default factory of field.
                setattr(self, f.name, f.default_factory())
            elif f.init:
                # No value specified and no default.
                raise TypeError(f"{cls.__name__}.__init__() missing required argument {f.name!r}")

        # Check for unexpected keyword parameters.
        if kwargs:
            for arg_name in kwargs:
                raise TypeError(
                    f"{cls.__name__}.__init__() got an unexpected keyword argument {arg_name!r}"
                )

    # Invoke dataclass decorator.
    cls = dataclasses.dataclass(init=False)(cls)

    # Add marker.
    cls.__qmi_configstruct__ = True  # type: ignore

    # Add __init__ method.
    cls.__init__ = initfn  # type: ignore

    # Return modified class.
    return cls


def config_struct_to_dict(cfg: Any) -> dict[str, Any]:
    """Convert configuration data from a dataclass instance to a dict.

    The returned dict will be suitable for serialization to JSON.

    Parameters:
        cfg: Configuration data (an instance of a dataclass).

    Returns:
        The configuration data converted to a dictionary.
    """

    if not dataclasses.is_dataclass(type(cfg)):
        raise TypeError("Configuration data must be a dataclass instance")

    ret = _inner_config_struct_to_dict(cfg)

    return ret


def _inner_config_struct_to_dict(cfg: Any) -> Any:
    """Inner recursive function that converts config_struct to dict"""
    if dataclasses.is_dataclass(type(cfg)):
        return _dictify_dataclass(cfg)
    elif isinstance(cfg, (list, tuple)):
        return _dictify_list_value(cfg)
    elif isinstance(cfg, dict):
        return _dictify_dict_value(cfg)
    elif (cfg is None) or isinstance(cfg, (int, float, bool, str)):
        return cfg
    else:
        raise TypeError(f"Unsupported value type: {cfg!r}")


def _dictify_list_value(cfg_list: list | tuple) -> list:
    """Copy a list value while converting its elements from structured to dict."""
    return [_inner_config_struct_to_dict(v) for v in cfg_list]


def _dictify_dict_value(cfg_dict: dict) -> dict:
    """Copy a dict value while converting its values from structured to dict."""
    ret: collections.OrderedDict = collections.OrderedDict()
    for (key, value) in cfg_dict.items():
        if not isinstance(key, str):
            raise TypeError(f"Unsupported non-string dictionary key: {key!r}")
        ret[key] = _inner_config_struct_to_dict(value)
    return ret


def _dictify_dataclass(cfg_dataclass: Any) -> dict:
    """Copy a dict value while converting its elements from dataclass to dict."""
    ret: collections.OrderedDict = collections.OrderedDict()
    for field in dataclasses.fields(cfg_dataclass):
        if hasattr(cfg_dataclass, field.name):
            value = getattr(cfg_dataclass, field.name)
            ret[field.name] = _inner_config_struct_to_dict(value)
    return ret


def _parse_config_value(val: Any, field_type: Any, path: list[str]) -> Any:
    """Convert JSON value to expected type."""

    # Recognize union of types, including None
    optional = False
    if " | " in repr(field_type):
        for t in field_type.__args__:
            if t == type(None):  # This is intentional! Do not change to 't is None' as it will fail
                optional = True
            else:
                field_type = t

    if field_type == Any:
        # This field allows any type; pass the actual value without conversion.
        return val

    if (val is None) and (optional or (field_type is None) or (field_type == type(None))):
        # This field accepts None and actual value is None; pass it.
        return val

    if (field_type in (int, float, str, bool)) and isinstance(val, field_type):
        # This field accepts the actual scalar value.
        return val

    if (field_type is float) and isinstance(val, int):
        # Implicit conversion of integer value to floating point.
        return float(val)

    # Recognize untyped "list", "tuple" and "dict" values.
    if (field_type in (list, tuple, dict)) and isinstance(val, field_type):
        return val

    # Recognize list[T].
    type_repr = repr(field_type)
    if type_repr.startswith("list["):
        (elem_type,) = field_type.__args__
        if isinstance(val, list):
            ret = []
            for (i, elem) in enumerate(val):
                path.append(f"[{i}]")
                ret.append(_parse_config_value(elem, elem_type, path))
                path.pop()
            return ret

    # Recognize tuple[...].
    if type_repr.startswith("tuple["):
        if (len(field_type.__args__) == 2) and (field_type.__args__[1] is Ellipsis):
            elem_type = field_type.__args__[0]
            if isinstance(val, (list, tuple)):
                ret = []
                for (i, elem) in enumerate(val):
                    path.append(f"[{i}]")
                    ret.append(_parse_config_value(elem, elem_type, path))
                    path.pop()
                return tuple(ret)
        elif len(val) == len(field_type.__args__):
            if isinstance(val, (list, tuple)) and (len(val) == len(field_type.__args__)):
                ret = []
                for (i, elem) in enumerate(val):
                    path.append(f"[{i}]")
                    ret.append(_parse_config_value(elem, field_type.__args__[i], path))
                    path.pop()
                return tuple(ret)

    # Recognize dict[str, T].
    if type_repr.startswith("dict[") and isinstance(val, dict):
        return _parse_config_dict(val, field_type, path)

    # Recognize data class.
    if dataclasses.is_dataclass(field_type):
        if isinstance(val, dict):
            return _parse_config_struct(val, field_type, path)
        elif dataclasses.is_dataclass(val) and not isinstance(val, type):
            return _parse_config_struct(dataclasses.asdict(val), field_type, path)

    pathstr = ".".join(path)
    raise QMI_ConfigurationException(
        f"Type mismatch in configuration item {pathstr}: got {type(val)} while expecting {field_type}"
    )


def _parse_config_dict(val: dict, field_type: Any, path: list[str]) -> _StrDict:
    """Parse Config Dict"""

    (_, elem_type) = field_type.__args__
    ret: _StrDict = collections.OrderedDict()
    for (k, elem) in val.items():
        if not isinstance(k, str):
            pathstr = ".".join(path)
            raise QMI_ConfigurationException(
                f"Unsupported non-string dictionary key {k!r} in configuration item {pathstr}"
            )
        path.append(f"[{k!r}]")
        ret[k] = _parse_config_value(elem, elem_type, path)
        path.pop()
    return ret


def _parse_config_struct(data: Any, cls: Any, path: list[str]) -> Any:
    """Convert dictionary to dataclass instance."""

    items: _StrDict = collections.OrderedDict()

    # Walk the list of field definitions.
    for f in dataclasses.fields(cls):
        if f.init and (f.name in data):
            # Value specified for this field.
            path.append(f.name)
            items[f.name] = _parse_config_value(data[f.name], f.type, path)
            path.pop()
        elif f.init and (f.default is dataclasses.MISSING)\
                and (f.default_factory is dataclasses.MISSING):  # type: ignore
            # Value not specified and no default.
            path.append(f.name)
            pathstr = ".".join(path)
            raise QMI_ConfigurationException(f"Missing value for required configuration item {pathstr}")

    # Check for left-over fields.
    for k in data.keys():
        if k not in items:
            path.append(k)
            pathstr = ".".join(path)
            raise QMI_ConfigurationException(f"Unknown configuration item {pathstr}")

    # Construct dataclass instance.
    return cls(**items)


def _check_config_struct_type(cls: Any, path: list[str]) -> None:
    """Check that the specified type is acceptable for configuration data."""

    pathstr = ".".join(path)

    # Recognize a union of types, including None.
    if " | " in repr(cls):
        nsub = 0
        for t in cls.__args__:
            if t == type(None):  # This is intentional! Do not change to 't is None' as it will fail
                pass
            elif nsub == 0:
                cls = t
                nsub += 1
            else:
                raise QMI_ConfigurationException(f"Unsupported Union type in configuration field {pathstr}")

    # Recognize scalar types.
    if cls in (int, float, str, bool):
        return  # accept

    # Recognize wildcard.
    if cls == Any:
        return  # accept

    # Recognize untyped aggregates.
    if cls in (list, dict, Any, tuple):
        return  # accept

    # Recognize list[T].
    type_repr = repr(cls)
    if type_repr.startswith("list["):
        (elem_type,) = cls.__args__
        path.append("[]")
        _check_config_struct_type(elem_type, path)
        path.pop()
        return  # accept

    # Recognize tuple[...].
    if type_repr.startswith("tuple["):
        if (len(cls.__args__) == 2) and (cls.__args__[1] is Ellipsis):
            elem_type = cls.__args__[0]
            path.append("[]")
            _check_config_struct_type(elem_type, path)
            path.pop()
            return  # accept
        else:
            for (i, elem_type) in enumerate(cls.__args__):
                path.append(f"[{i}]")
                _check_config_struct_type(elem_type, path)
                path.pop()
            return  # accept

    # Recognize dict[str, T].
    if type_repr.startswith("dict["):
        (key_type, elem_type) = cls.__args__
        if key_type is not str:
            raise QMI_ConfigurationException(
                f"Unsupported non-string-key dictionary type in configuration field {pathstr}"
            )
        path.append("[]")
        _check_config_struct_type(elem_type, path)
        path.pop()
        return  # accept

    # Recognize data class.
    if dataclasses.is_dataclass(cls) and isinstance(cls, type):
        # Check each field type.
        for f in dataclasses.fields(cls):
            if f.init:
                path.append(f.name)
                _check_config_struct_type(f.type, path)
                path.pop()
        return  # accept

    # Reject.
    raise QMI_ConfigurationException(f"Unsupported data type in configuration field {pathstr}")


def config_struct_from_dict(data: _StrDict, cls: type[_T]) -> _T:
    """Convert configuration data from a dictionary to a dataclass instance.

    The input data is typically obtained by parsing a JSON file.

    Parameters:
        data: Configuration data as a dict instance.
        cls: Dataclass type to be used for holding the configuration data.

    Returns:
        An instance of the specified dataclass containing the configuration data.

    Raises:
        ~qmi.core.exceptions.QMI_ConfigurationException: If the
            configuration data does not match the expected structure.
    """

    if (not dataclasses.is_dataclass(cls)) or (not isinstance(cls, type)):
        raise TypeError("Configuration class type must be a dataclass")

    # Verify that the dataclass type contains only supported field types.
    _check_config_struct_type(cls, [])

    # Convert dictionary items to structure field assignments.
    return _parse_config_struct(data, cls, [])
