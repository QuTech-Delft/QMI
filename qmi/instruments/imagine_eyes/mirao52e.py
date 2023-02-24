"""Instrument driver for the Imagine Eyes Mirao52e deformable mirror."""

import sys
import logging
import os
import re
import subprocess
from pathlib import Path

from typing import List, NamedTuple, Optional

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


# Named tuple representing mirror status.
MirrorStatus = NamedTuple("MirrorStatus", [
    ("psu_temp", float),
    ("locked", bool)
])


def read_mirao_file(filename: str) -> List[float]:
    """Read a set of mirror actuator values from an MRO file.

    The MRO files can be generated with the MroEdit tool.

    :param filename: File name of the MRO file.
    :return: List of 52 floating point values.
    """
    ret = 52 * [0.0]
    with open(filename, "r") as f:
        s = f.readline()
        s = s.strip()
        while (s.startswith("DLL_VERSION")
               or s.startswith("FILE_FORMAT_VERSION")
               or s.startswith("CREATION_DATE")
               or s.startswith("DISTRIBUTOR")):
            s = f.readline()
            s = s.strip()
        for i in range(52):
            m = re.match(r"^A([0-9]{2}):\s*([0-9a-fA-F]{4})\s*$", s)
            if not m:
                raise ValueError("Unexpected syntax in MRO file: {}".format(s))
            a = int(m.group(1))
            v = int(m.group(2), 16)
            if a != i:
                raise ValueError("Unexpected order of actuators in MRO file")
            if v > 0x3FFF:
                raise ValueError("Out-of-range actuator value in MRO file: 0x{:04x}".format(v))
            ret[i] = (v - 0x1FFF) / 8192.0
            s = f.readline()
            s = s.strip()
        if s != "END":
            raise ValueError("Unexpected syntax in MRO file: {}".format(s))
    return ret


class ImagineEyes_Mirao52e(QMI_Instrument):
    """Instrument driver for the Imagine Eyes Mirao52e deformable mirror.

    Note that the deformable mirror will only hold its actuator positions
    while the connection to the instrument is open. Closing the connection
    will automatically return the mirror to its free state (which is not flat).

    This driver communicates with the deformable mirror via
    a helper program "mirao_bridge.exe".

    The helper program is a command-line Windows application.
    On Linux, it can run under Wine.
    """

    # Location of bridge program.
    DEFAULT_BRIDGE_DIR = os.path.join(Path.home(), "mirao")
    BRIDGE_CMD = "mirao_bridge.exe"

    # USD vendor ID : product ID of the deformable mirror.
    USB_ID = "0403:6001"

    def __init__(self, context: QMI_Context, name: str, bridge_dir: str = DEFAULT_BRIDGE_DIR) -> None:
        """Initialize the driver.

        :param name: Name for this instrument instance.
        :param bridge_dir: Path to directory where mirao_bridge.exe is installed.
        """
        if not os.path.isdir(bridge_dir):
            raise QMI_InstrumentException("Mirao helper directory {!r} not found".format(bridge_dir))

        super().__init__(context, name)
        self._bridge_dir = bridge_dir
        self._proc = None  # type: Optional[subprocess.Popen]
        self._version_string = ""

    def _start_helper(self) -> None:
        """Start the helper program under native Windows."""
        assert self._proc is None
        self._proc = subprocess.Popen(args=self.BRIDGE_CMD,
                                      stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE,
                                      cwd=self._bridge_dir)

    def _start_helper_wine(self) -> None:
        """Start the helper program under wine."""
        assert self._proc is None
        env: dict = {}
        env.update(os.environ)
        env["WINEDLLPATH"] = "."
        env["FTDID"] = self.USB_ID
        self._proc = subprocess.Popen(args=["wine", self.BRIDGE_CMD],
                                      stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE,
                                      cwd=self._bridge_dir,
                                      env=env)
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None

    def _stop_helper(self) -> None:
        """Stop the helper program."""
        assert self._proc is not None
        assert self._proc.stdin is not None
        assert self._proc.stdout is not None
        self._proc.stdin.close()
        self._proc.wait()
        self._proc.stdout.close()
        self._proc = None
        self._version_string = ""

    def _recv_response(self) -> List[str]:
        """Read response from helper program."""
        assert self._proc is not None
        assert self._proc.stdout is not None
        ret: List[str] = []
        while True:
            s = self._proc.stdout.readline()
            if not s:
                raise QMI_InstrumentException("Unexpected end of input from helper program")
            s = s.strip()
            _logger.debug("recv: %s", s)
            if s == b"READY":
                return ret
            ret.append(s.decode("latin1"))

    def _recv_handshake(self) -> None:
        """Receive handshake message from helper program."""
        lines = self._recv_response()
        if len(lines) == 1:
            w = lines[0].split()
            if len(w) == 2 and w[0] == "MIRAO52_BRIDGE":
                self._version_string = w[1]
                return
        raise QMI_InstrumentException("Unexpected handshake from helper program: {}".format(lines))

    def _send_cmd(self, cmd: str) -> None:
        """Send command to helper program and check response."""
        assert self._proc is not None
        assert self._proc.stdin is not None
        self._proc.stdin.write(cmd.encode("ascii") + b"\r\n")
        self._proc.stdin.flush()

    def _check_response(self) -> None:
        lines = self._recv_response()
        got_ok = False
        for s in lines:
            if s == "OK":
                got_ok = True
            if s.startswith("ERROR "):
                raise QMI_InstrumentException("Error from {}: {}".format(self._name, s[6:]))
        if not got_ok:
            raise QMI_InstrumentException("Unexpected response from {}: {}".format(self._name, lines))

    @rpc_method
    def open(self) -> None:

        self._check_is_closed()

        _logger.info("[%s] Starting helper program", self._name)

        if sys.platform.startswith("linux"):
            self._start_helper_wine()
        else:
            self._start_helper()

        try:
            self._recv_handshake()
            _logger.info("[%s] Opening connection to instrument", self._name)
            self._send_cmd("OPEN")
            self._check_response()
        except Exception:
            # Shut down helper program when an error occurs.
            self._stop_helper()
            raise

        super().open()

    @rpc_method
    def close(self) -> None:
        self._check_is_open()
        _logger.info("[%s] Closing connection to instrument", self._name)
        try:
            self._send_cmd("CLOSE")
            self._check_response()
        finally:
            _logger.info("[%s] Stopping helper program", self._name)
            self._stop_helper()
            super().close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Read instrument type and version and return QMI_InstrumentIdentification instance."""
        self._check_is_open()
        return QMI_InstrumentIdentification(vendor="ImagineEyes",
                                            model="Mirao52e",
                                            serial=None,
                                            version=self._version_string)

    @rpc_method
    def apply(self, actuators: List[float]) -> None:
        """Apply actuator values.

        :param actuators: List of 52 floating point values.
        """
        self._check_is_open()
        _logger.debug("[%s] Applying actuator values", self._name)
        if len(actuators) != 52:
            raise QMI_UsageException("Expecting 52 actuator values")
        cmd = "APPLY " + ",".join("{:.6f}".format(v) for v in actuators)
        self._send_cmd(cmd)
        self._check_response()

    @rpc_method
    def get_mirror_status(self) -> MirrorStatus:
        """Return the mirror status.

        :return: Named tuple (psu_temperature, locked)
            where psu_temperature is the PSU temperature in Celsius;
            locked is True if the mirror is locked due to an error condition.
        """
        self._check_is_open()
        self._send_cmd("MONITOR")
        lines = self._recv_response()
        psu_temp = 0.0
        locked = False
        got_resp = False
        for s in lines:
            m = re.match(r"^PSUTEMP=([0-9.]+) LOCKED=([01])$", s)
            if m:
                psu_temp = float(m.group(1))
                locked = (int(m.group(2)) != 0)
                got_resp = True
            if s.startswith("ERROR "):
                raise QMI_InstrumentException("Error from {}: {}".format(self._name, s[6:]))
        if not got_resp:
            raise QMI_InstrumentException("Unexpected response from {}: {}".format(self._name, lines))
        return MirrorStatus(psu_temp=psu_temp, locked=locked)
