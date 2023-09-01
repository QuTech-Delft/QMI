"""Test for the Boston MicroMachines Multi-DM series deformable mirror QMI driver."""

import logging

from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch
from unittest.mock import call

from typing import cast
from dataclasses import dataclass

from qmi.instruments.boston_micromachines.multidm import BostonMicromachines_MultiDM
from qmi.instruments.boston_micromachines.multidm import read_mirror_shape
from qmi.instruments.boston_micromachines.multidm import write_mirror_shape
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.exceptions import QMI_UsageException


# Disable all logging
logging.disable(logging.CRITICAL)


@dataclass
class TestMeta:
    """Test meta data."""

    name: MagicMock
    serial_number: MagicMock
    set_shape_prog: MagicMock
    super: MagicMock
    instr: BostonMicromachines_MultiDM


class TestReadMirrorShape(TestCase):
    def test_read_mirror_shape(self):
        """read_mirror_shape(), happy flow"""
        mock_file_name = MagicMock()
        mock_file = MagicMock()
        mock_file.readline = MagicMock(side_effect=["0.1\r\n"] * 3 + [None])
        mock_file.__enter__.return_value = mock_file
        mock_open = MagicMock(return_value=mock_file)
        with patch("qmi.instruments.boston_micromachines.multidm.open", mock_open):
            rt_val = read_mirror_shape(mock_file_name)
        mock_open.assert_called_once_with(mock_file_name, "r")
        self.assertEqual(rt_val, [0.1] * 3)


class TestWriteMirrorShape(TestCase):
    def test_write_mirror_shape(self):
        """write_mirror_shape(), happy flow"""
        mock_file_name = MagicMock()
        mock_shape = [0.1, 0.2, 0.3]
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_open = MagicMock(return_value=mock_file)
        mock_print = MagicMock()
        with patch(
            "qmi.instruments.boston_micromachines.multidm.open", mock_open
        ), patch("qmi.instruments.boston_micromachines.multidm.print", mock_print):
            write_mirror_shape(mock_file_name, mock_shape)
        mock_open.assert_called_once_with(mock_file_name, "w")
        mock_print.assert_has_calls(
            [call(f"{i:.9f}", file=mock_file) for i in mock_shape]
        )


class TestBostonMicromachinesMultiDM(TestCase):
    """Testcase for the BostonMicromachines_MultiDM class."""

    def setUp(self):
        mock_name = MagicMock()
        mock_serial_number = "12345678910"
        mock_set_shape_prog = MagicMock()
        mock_super = MagicMock()

        instr = BostonMicromachines_MultiDM(
            MagicMock(), mock_name, mock_serial_number, mock_set_shape_prog
        )

        self._patcher_super = patch(
            "qmi.instruments.boston_micromachines.multidm.super", mock_super
        )
        self._patcher_super.start()

        self._meta = TestMeta(
            instr=cast(BostonMicromachines_MultiDM, instr),
            name=mock_name,
            serial_number=mock_serial_number,
            set_shape_prog=mock_set_shape_prog,
            super=mock_super,
        )

    def tearDown(self):
        self._meta = None
        self._patcher_super.stop()

    def test_init(self):
        """BostonMicromachines_MultiDM.__init__(), happy flow"""

        self.assertEqual(self._meta.instr._serial_number, self._meta.serial_number)
        self.assertEqual(self._meta.instr._set_shape_prog, self._meta.set_shape_prog)

    def test_init_invalid_serial_len(self):
        """BostonMicromachines_MultiDM.__init__(), invalid serial length"""
        mock_serial_number = "1234567891"

        with self.assertRaises(QMI_InstrumentException):
            BostonMicromachines_MultiDM(
                MagicMock(), MagicMock(), mock_serial_number, MagicMock()
            )

    def test_init_invalid_serial_character(self):
        """BostonMicromachines_MultiDM.__init__(), invalid serial character"""
        mock_serial_number = "1234567891!"

        with self.assertRaises(QMI_InstrumentException):
            BostonMicromachines_MultiDM(
                MagicMock(), MagicMock(), mock_serial_number, MagicMock()
            )

    def test_run_set_shape_prog(self):
        """BostonMicromachines_MultiDM._run_set_shape_prog(), happy flow"""
        mock_shape = [0.001, 0.002, 0.003]
        mock_subprocess = MagicMock()
        mock_proc = MagicMock()
        mock_subprocess.Popen = MagicMock(return_value=mock_proc)
        mock_helper_output = "OK\nOK\nOK\n".encode("latin1")
        mock_helper_input = MagicMock()
        mock_proc.communicate = MagicMock(
            return_value=(mock_helper_output, mock_helper_input)
        )
        mock_proc.returncode = 0

        with patch(
            "qmi.instruments.boston_micromachines.multidm.subprocess", mock_subprocess
        ):
            self._meta.instr._run_set_shape_prog(mock_shape)

        mock_subprocess.Popen.assert_called_once_with(
            args=[self._meta.set_shape_prog, "-s", self._meta.serial_number, "-i"],
            stdin=mock_subprocess.PIPE,
            stdout=mock_subprocess.PIPE,
        )
        mock_proc.kill.assert_called_once_with()
        mock_proc.stdin.close.assert_called_once_with()
        mock_proc.wait.assert_called_once_with()
        mock_proc.stdout.close.assert_called_once_with()

    def test_run_set_shape_prog_helper_error(self):
        """BostonMicromachines_MultiDM._run_set_shape_prog(), helper errors handling."""
        mock_shape = [0.001, 0.002, 0.003]
        mock_helper_output = "ERROR\nOK\nOK\n".encode("latin1")

        mock_subprocess = MagicMock()
        mock_proc = MagicMock()
        mock_subprocess.Popen = MagicMock(return_value=mock_proc)
        mock_helper_input = MagicMock()
        mock_proc.communicate = MagicMock(
            return_value=(mock_helper_output, mock_helper_input)
        )
        mock_proc.returncode = 0

        with patch(
            "qmi.instruments.boston_micromachines.multidm.subprocess", mock_subprocess
        ):
            with self.assertRaises(QMI_InstrumentException):
                self._meta.instr._run_set_shape_prog(mock_shape)

        mock_subprocess.Popen.assert_called_once_with(
            args=[self._meta.set_shape_prog, "-s", self._meta.serial_number, "-i"],
            stdin=mock_subprocess.PIPE,
            stdout=mock_subprocess.PIPE,
        )
        mock_proc.kill.assert_called_once_with()
        mock_proc.stdin.close.assert_called_once_with()
        mock_proc.wait.assert_called_once_with()
        mock_proc.stdout.close.assert_called_once_with()

    def test_run_set_shape_prog_communicate_failure(self):
        """BostonMicromachines_MultiDM._run_set_shape_prog(), communicate failure handling."""
        mock_shape = [0.001, 0.002, 0.003]
        mock_helper_output = "OK\nOK\nOK\n".encode("latin1")
        mock_subprocess = MagicMock()
        mock_proc = MagicMock()
        mock_subprocess.Popen = MagicMock(return_value=mock_proc)
        mock_helper_input = MagicMock()
        mock_proc.communicate = MagicMock(
            return_value=(mock_helper_output, mock_helper_input)
        )
        mock_proc.returncode = 1

        with patch(
            "qmi.instruments.boston_micromachines.multidm.subprocess", mock_subprocess
        ):
            with self.assertRaises(QMI_InstrumentException):
                self._meta.instr._run_set_shape_prog(mock_shape)

        mock_subprocess.Popen.assert_called_once_with(
            args=[self._meta.set_shape_prog, "-s", self._meta.serial_number, "-i"],
            stdin=mock_subprocess.PIPE,
            stdout=mock_subprocess.PIPE,
        )
        mock_proc.kill.assert_called_once_with()
        mock_proc.stdin.close.assert_called_once_with()
        mock_proc.wait.assert_called_once_with()
        mock_proc.stdout.close.assert_called_once_with()

    def test_open(self):
        """BostonMicromachines_MultiDM.open(), happy flow."""
        mock_isfile = MagicMock()
        with patch(
            "qmi.instruments.boston_micromachines.multidm.os.path.isfile", mock_isfile
        ):
            self._meta.instr.open()
        self._meta.super().open.assert_called_once_with()
        mock_isfile.assert_called_once_with(self._meta.set_shape_prog)

    def test_open_invalid_path(self):
        """BostonMicromachines_MultiDM.open(), invalid path handling."""
        mock_isfile = MagicMock(return_value=False)
        with patch(
            "qmi.instruments.boston_micromachines.multidm.os.path.isfile", mock_isfile
        ):
            with self.assertRaises(QMI_InstrumentException):
                self._meta.instr.open()
        mock_isfile.assert_called_once_with(self._meta.set_shape_prog)

    def test_apply(self):
        """BostonMicromachines_MultiDM.apply(), happy flow."""
        mock_shape = [0.01] * 140

        self._meta.instr._check_is_open = MagicMock()
        self._meta.instr._run_set_shape_prog = MagicMock()

        self._meta.instr.apply(mock_shape)

        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.instr._run_set_shape_prog.assert_called_once_with(mock_shape)

    def test_apply_invalid_shape_len(self):
        """BostonMicromachines_MultiDM.apply(), invalid shape len handling."""
        mock_shape = []

        self._meta.instr._check_is_open = MagicMock()
        with self.assertRaises(QMI_UsageException):
            self._meta.instr.apply(mock_shape)

        self._meta.instr._check_is_open.assert_called_once_with()

    def test_apply_value_to_high(self):
        """BostonMicromachines_MultiDM.apply(), value too high."""
        mock_shape = [0.01] * 139 + [1.1]

        self._meta.instr._check_is_open = MagicMock()
        with self.assertRaises(QMI_UsageException):
            self._meta.instr.apply(mock_shape)

        self._meta.instr._check_is_open.assert_called_once_with()

    def test_apply_value_to_low(self):
        """BostonMicromachines_MultiDM.apply(), value too low."""
        mock_shape = [0.01] * 139 + [-0.1]

        self._meta.instr._check_is_open = MagicMock()
        with self.assertRaises(QMI_UsageException):
            self._meta.instr.apply(mock_shape)

        self._meta.instr._check_is_open.assert_called_once_with()
