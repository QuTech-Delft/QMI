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
 - ``List[T]`` where `T` is a supported field type
 - ``Dict[str, T]`` where `T` is a supported field type
 - ``Tuple[T1, T2, T3]`` or ``Tuple[T, ...]`` where `T`, `T1`, etc are supported field types
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

from typing import Any, Dict, List, Tuple, TypeVar, Type, Union

from qmi.core.exceptions import QMI_ConfigurationException

_T = TypeVar("_T")
_StrDict = Dict[str, Any]


def configstruct(cls: Type[_T]) -> Type[_T]:
    """Class decorator to mark classes that hold QMI configuration data.

    This decorator is based on the standard `@dataclass` decorator.
    It calls ``@dataclass(init=False)`` to do most of the work,
    then adds a custom `__init__()` method.
    """

    # New __init__() function for the class.
    def initfn(self: Any, **kwargs: Any) -> None:

        # Walk the list of field definitions.
        for f in dataclasses.fields(cls):   # type: ignore
            if f.init and f.name in kwargs:
                # Value specified as argument to __init__().
                value = kwargs.pop(f.name)
                _parse_config_value(value, f.type, [])
                setattr(self, f.name, value)
            elif f.default is not dataclasses.MISSING:
                # No value specified; use default value of field.
                setattr(self, f.name, f.default)
            elif f.default_factory is not dataclasses.MISSING: # type: ignore
                # No value specified; use default factory of field.
                setattr(self, f.name, f.default_factory()) # type: ignore
            elif f.init:
                # No value specified and no default.
                raise TypeError("{}.__init__() missing required argument {!r}"
                                .format(cls.__name__, f.name))

        # Check for unexpected keyword parameters.
        if kwargs:
            for arg_name in kwargs:
                raise TypeError(
                    "{}.__init__() got an unexpected keyword argument {!r}"
                    .format(cls.__name__, arg_name))

    # Invoke dataclass decorator.
    cls = dataclasses.dataclass(init=False)(cls)

    # Add marker.
    cls.__qmi_configstruct__ = True  # type: ignore

    # Add __init__ method.
    cls.__init__ = initfn  # type: ignore

    # Return modified class.
    return cls


def config_struct_to_dict(cfg: Any) -> Dict[str, Any]:
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
        raise TypeError("Unsupported value type: {!r}".format(cfg))


def _dictify_list_value(cfg_list: Union[list, tuple]) -> list:
    """Copy a list value while converting its elements from structured to dict."""
    return [_inner_config_struct_to_dict(v) for v in cfg_list]


def _dictify_dict_value(cfg_dict: dict) -> dict:
    """Copy a dict value while converting its values from structured to dict."""
    ret: collections.OrderedDict = collections.OrderedDict()
    for (key, value) in cfg_dict.items():
        if not isinstance(key, str):
            raise TypeError("Unsupported non-string dictionary key: {!r}".format(key))
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


def _parse_config_value(val: Any, field_type: Any, path: List[str]) -> Any:
    """Convert JSON value to expected type."""

    # Recognize Optional[T]
    optional = False
    if repr(field_type).startswith("typing.Union[") or repr(field_type).startswith("typing.Optional["):
        for t in field_type.__args__:
            if t == type(None):
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

    # Recognize "List" and "Dict" and map them to "list" and "dict".
    if field_type == List:
        field_type = list
    elif field_type == Tuple:
        field_type = tuple
    elif field_type == Dict:
        field_type = dict

    # Recognize untyped "list" and "dict" values.
    if (field_type in (list, dict)) and isinstance(val, field_type):
        return val

    # Recognize untyped "tuple" values.
    if (field_type is tuple) and isinstance(val, list):
        return tuple(val)

    # Recognize List[T].
    type_repr = repr(field_type)
    if type_repr.startswith("typing.List["):
        (elem_type,) = field_type.__args__
        if isinstance(val, list):
            ret = []
            for (i, elem) in enumerate(val):
                path.append("[{}]".format(i))
                ret.append(_parse_config_value(elem, elem_type, path))
                path.pop()
            return ret

    # Recognize Tuple[...].
    if type_repr.startswith("typing.Tuple["):
        if (len(field_type.__args__) == 2) and (field_type.__args__[1] is Ellipsis):
            elem_type = field_type.__args__[0]
            if isinstance(val, (list, tuple)):
                ret = []
                for (i, elem) in enumerate(val):
                    path.append("[{}]".format(i))
                    ret.append(_parse_config_value(elem, elem_type, path))
                    path.pop()
                return tuple(ret)
        elif len(val) == len(field_type.__args__):
            if isinstance(val, (list, tuple)) and (len(val) == len(field_type.__args__)):
                ret = []
                for (i, elem) in enumerate(val):
                    path.append("[{}]".format(i))
                    ret.append(_parse_config_value(elem, field_type.__args__[i], path))
                    path.pop()
                return tuple(ret)

    # Recognize Dict[str, T].
    if type_repr.startswith("typing.Dict[") and isinstance(val, dict):
        return _parse_config_dict(val, field_type, path)

    # Recognize data class.
    if dataclasses.is_dataclass(field_type):
        if isinstance(val, dict):
            return _parse_config_struct(val, field_type, path)
        elif dataclasses.is_dataclass(val):
            return _parse_config_struct(dataclasses.asdict(val), field_type, path)

    pathstr = ".".join(path)
    raise QMI_ConfigurationException("Type mismatch in configuration item {}: got {} while expecting {}"
                                     .format(pathstr, type(val), field_type))


def _parse_config_dict(val: dict, field_type: Any, path: List[str]) -> _StrDict:
    """Parse Config Dict"""

    (_, elem_type) = field_type.__args__
    ret = collections.OrderedDict() # type: _StrDict
    for (k, elem) in val.items():
        if not isinstance(k, str):
            pathstr = ".".join(path)
            raise QMI_ConfigurationException(
                "Unsupported non-string dictionary key {!r} in configuration item {}"
                .format(k, pathstr))
        path.append("[{!r}]".format(k))
        ret[k] = _parse_config_value(elem, elem_type, path)
        path.pop()
    return ret


def _parse_config_struct(data: Any, cls: Any, path: List[str]) -> Any:
    """Convert dictionary to dataclass instance."""

    items = collections.OrderedDict() # type: _StrDict

    # Walk the list of field definitions.
    for f in dataclasses.fields(cls):
        if f.init and (f.name in data):
            # Value specified for this field.
            path.append(f.name)
            items[f.name] = _parse_config_value(data[f.name], f.type, path)
            path.pop()
        elif f.init and (f.default is dataclasses.MISSING) \
                    and (f.default_factory is dataclasses.MISSING): # type: ignore
            # Value not specified and no default.
            path.append(f.name)
            pathstr = ".".join(path)
            raise QMI_ConfigurationException("Missing value for required configuration item {}".format(pathstr))

    # Check for left-over fields.
    for k in data.keys():
        if k not in items:
            path.append(k)
            pathstr = ".".join(path)
            raise QMI_ConfigurationException("Unknown configuration item {}".format(pathstr))

    # Construct dataclass instance.
    return cls(**items)


def _check_config_struct_type(cls: Any, path: List[str]) -> None:
    """Check that the specified type is acceptable for configuration data."""

    pathstr = ".".join(path)

    # Recognize Optional[T]
    if repr(cls).startswith("typing.Union[") or repr(cls).startswith("typing.Optional["):
        nsub = 0
        for t in cls.__args__:
            if t == type(None):
                pass
            elif nsub == 0:
                cls = t
                nsub += 1
            else:
                raise QMI_ConfigurationException("Unsupported Union type in configuration field {}".format(pathstr))

    # Recognize scalar types.
    if cls in (int, float, str, bool):
        return  # accept

    # Recognize wildcard.
    if cls == Any:
        return  # accept

    # Recognize untyped aggregates.
    if cls in (list, dict, Any, List, Tuple, Dict):
        return  # accept

    # Recognize List[T].
    type_repr = repr(cls)
    if type_repr.startswith("typing.List["):
        (elem_type,) = cls.__args__
        path.append("[]")
        _check_config_struct_type(elem_type, path)
        path.pop()
        return  # accept

    # Recognize Tuple[...].
    if type_repr.startswith("typing.Tuple["):
        if (len(cls.__args__) == 2) and (cls.__args__[1] is Ellipsis):
            elem_type = cls.__args__[0]
            path.append("[]")
            _check_config_struct_type(elem_type, path)
            path.pop()
            return  # accept
        else:
            for (i, elem_type) in enumerate(cls.__args__):
                path.append("[{}]".format(i))
                _check_config_struct_type(elem_type, path)
                path.pop()
            return  # accept

    # Recognize Dict[str, T].
    if type_repr.startswith("typing.Dict["):
        (key_type, elem_type) = cls.__args__
        if key_type is not str:
            raise QMI_ConfigurationException("Unsupported non-string-key dictionary type in configuration field {}"
                                             .format(pathstr))
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
    raise QMI_ConfigurationException("Unsupported data type in configuration field {}".format(pathstr))


def config_struct_from_dict(data: _StrDict, cls: Type[_T]) -> _T:
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
