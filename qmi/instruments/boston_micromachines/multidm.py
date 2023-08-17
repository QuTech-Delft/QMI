"""Instrument driver for Boston Micromachines Multi-DM series deformable mirror.

This driver depends on a custom helper program to access the deformable mirror.
The helper program is written in C and links with the Boston Micromachines
libraries to access the mirror via USB.

See `qmi/toolage/boston_micromachines_multidm/` for the source code of this helper program.
"""

import logging
import os
import os.path
import re
import subprocess

from typing import List

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException
from qmi.core.instrument import QMI_Instrument
from qmi.core.rpc import rpc_method


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


def read_mirror_shape(file_name: str) -> List[float]:
    """Read a mirror shape from a file.

    This function expects the file in the same format used by the
    Boston Micromachines software: a plain text file containing one line
    per actuator, each line containing a single floating point number.

    Parameters:
        file_name: Name of the file to read.

    Returns:
        List of actuator values in the range 0.0 to 1.0.
    """
    shape: List[float] = []
    with open(file_name, "r") as file_handle:
        while True:
            s = file_handle.readline()
            if not s:
                break
            v = float(s.strip())
            shape.append(v)
    return shape


def write_mirror_shape(file_name: str, shape: List[float]) -> None:
    """Write mirror shape to a file.

    Parameters:
        file_name: Name of file to write.
        shape: List of 140 floating point values describing the displacement of each actuator
            as a value in the range 0.0 to 1.0.
    """
    with open(file_name, "w") as file_handle:
        for shape_val in shape:
            print("{:.9f}".format(shape_val), file=file_handle)


class BostonMicromachines_MultiDM(QMI_Instrument):
    """Instrument driver for the Boston Micromachines Multi-DM series deformable mirrors.

    This driver was developed for the DM140A, but is expected to also work
    with other Multi-DM models with 140 actuators.

    This drives communicates with the deformable mirror via an external
    helper program `boston_micromachines_multidm_set_shape`.
    """

    # Number of actuators in the deformable mirror.
    NUMBER_OF_ACTUATORS = 140

    # Expected length of the serial number string.
    BMC_SERIAL_NUMBER_LEN = 11

    # Timeout for running the set_shape helper program (seconds).
    SET_SHAPE_TIMEOUT = 10

    def __init__(self, context: QMI_Context, name: str, serial_number: str, set_shape_prog: str) -> None:
        """Initialize the driver.

        Parameters:
            name: Name for this instrument instance.
            serial_number: Serial number of the deformable mirror.
            set_shape_prog: Location of helper program to load a mirror shape.

        Raises:
            QMI_InstrumentException: By invalid serial number length or string.
        """

        if len(serial_number) != self.BMC_SERIAL_NUMBER_LEN:
            raise QMI_InstrumentException("Invalid serial number {!r}, expecting {} characters"
                                          .format(serial_number, self.BMC_SERIAL_NUMBER_LEN))

        if not re.match(r"^[-0-9A-Za-z#]+$", serial_number):
            raise QMI_InstrumentException("Invalid serial number {!r}".format(serial_number))

        super().__init__(context, name)
        self._serial_number = serial_number
        self._set_shape_prog = set_shape_prog

    def _run_set_shape_prog(self, shape: List[float]) -> None:
        """Run the helper program to load the specified mirror shape."""

        # Serialize the mirror shape to a string for the helper program.
        # One line per actuator holding a floatping point value.
        helper_input = b"".join([(b"%.9f\n" % shape_val) for shape_val in shape ])

        # Prepare command line to start the helper program.
        args = [self._set_shape_prog, "-s", self._serial_number, "-i"]

        _logger.info("[%s] Running helper program %s", self._name, " ".join([repr(arg) for arg in args]))

        # Start the helper program.
        proc = subprocess.Popen(args=args,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE)

        assert proc.stdin is not None
        assert proc.stdout is not None

        try:

            # Provide input to helper program and capture output from program.
            (helper_output, _) = proc.communicate(input=helper_input, timeout=self.SET_SHAPE_TIMEOUT)

            # Check for error messages in the output from the program.
            output_str = helper_output.decode('latin1')
            for output_line in output_str.splitlines():
                _logger.debug("helper: %s", output_line)

                # Any line starting with "ERROR" indicates an irrecoverable error.
                if output_line.startswith("ERROR"):
                    raise QMI_InstrumentException("Helper program failed: {}".format(output_line))

            # Check exit status of helper program.
            if proc.returncode != 0:
                raise QMI_InstrumentException("Helper program returned exit status {}".format(proc.returncode))

        finally:
            # Whatever happened (success or failure), we need to make sure
            # the program stops and input/output redirection is cleaned up.
            proc.kill()

            proc.stdin.close()
            proc.wait()
            proc.stdout.close()

        _logger.debug("[%s] Helper program successful", self._name)

    @rpc_method
    def open(self) -> None:

        # Nothing actually needs to be done to "open" the mirror.
        # There is no sense in which we can access the mirror device until
        # the point where we activate a mirror shape.
        #
        # Instead of "opening" the device, we just check that the
        # helper program is installed on the system.

        if not os.path.isfile(self._set_shape_prog):
            raise QMI_InstrumentException("Helper program {!r} not found".format(self._set_shape_prog))

        super().open()

    @rpc_method
    def apply(self, shape: List[float]) -> None:
        """Apply actuator values.

        Parameters:
            shape: List of 140 floating point values describing the displacement of each actuator
                as a value in the range 0.0 to 1.0.

        Note that the shape values represent the raw, uncalibrated values sent to the mirror actuators.
        The actual shape of the mirror will be affected by offset mismatch and by interaction
        between neighbouring actuators.
        """
        self._check_is_open()

        if len(shape) != self.NUMBER_OF_ACTUATORS:
            raise QMI_UsageException("Expecting {} actuator values".format(self.NUMBER_OF_ACTUATORS))

        if min(shape) < 0.0 or max(shape) > 1.0:
            raise QMI_UsageException("Expecting actuator values between 0.0 and 1.0")

        _logger.debug("[%s] Applying mirror shape", self._name)

        # Run BMCLoadShape to load the mirror shape.
        self._run_set_shape_prog(shape)
