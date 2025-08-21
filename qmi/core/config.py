"""Read and process configuration files.

The QMI configuration file language closely resembles JSON.
The configuration language differs from JSON as follows:

- The top-level value in the file must be a dictionary
  (the JSON specification calls this an `object`).
- Comments are allowed (and ignored during reading).
- Comments start with ``#`` and continue until the end of the line.
- Comments can not be placed inside strings.
"""

import collections
import json
import re

from qmi.core.exceptions import QMI_ConfigurationException


def _strip_comments(s: str) -> str:
    """Strip comments from a JSON-like string."""

    # Match first # character (excluding strings).
    re_comment = re.compile(r'^(?:[^"#]|"(?:[^\\"]|\\.)*")*#')

    # Split into lines.
    lines = re.split(r'[\r\n]', s)

    # Process each line.
    for (i, line) in enumerate(lines):
        # Strip comments from this line.
        if "#" in line:
            m = re_comment.match(line)
            if m is not None:
                # Found comment. Strip it.
                lines[i] = line[:m.end()-1]

    # Join lines to form stripped string.
    return "\n".join(lines)


def config_pairs_hook(config_pairs) -> collections.OrderedDict:
    """Reject duplicate keys."""
    cfg_dict = collections.OrderedDict()
    for k, v in config_pairs:
        if k in cfg_dict:
            raise ValueError(f"duplicate key: {k}")

        else:
            cfg_dict[k] = v

    return cfg_dict


def load_config_string(s: str) -> dict:
    """Load configuration data from a string.

    Parameters:
        s: String containing configuration data.

    Returns:
        Parsed configuration data checked for duplicates.
    """

    s = _strip_comments(s)
    cfg = json.loads(s, object_pairs_hook=config_pairs_hook)
    if not isinstance(cfg, dict):
        raise QMI_ConfigurationException("Expecting mapping at top level of configuration but got {}"
                                         .format(type(cfg).__name__))

    return cfg


def load_config_file(filename: str) -> dict:
    """Load configuration data from a file.

    Parameters:
        filename: Path of configuration file.

    Returns:
        Parsed configuration data.
    """
    with open(filename, "r") as f:
        s = f.read()
    return load_config_string(s)


def dump_config_string(cfg: dict) -> str:
    """Serialize configuration data to a string.

    Parameters:
        cfg: Configuration data.

    Returns:
        Serialized configuration string.
    """

    if not isinstance(cfg, dict):
        raise QMI_ConfigurationException("Expecting mapping at top level of configuration but got {}"
                                         .format(type(cfg).__name__))

    return json.dumps(cfg, indent=4)


def dump_config_file(cfg: dict, filename: str) -> None:
    """Write configuration data to a file.

    Parameters:
        cfg: Configuration data.
        filename: Path of configuration file to write.
    """
    s = dump_config_string(cfg)
    with open(filename, "w") as f:
        f.write(s)
