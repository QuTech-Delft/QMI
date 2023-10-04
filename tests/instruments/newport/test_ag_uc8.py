"""Unit-tests for the New AG UC8 QMI driver."""

import logging

from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch
from unittest.mock import call

from typing import cast
from dataclasses import dataclass

from qmi.core.transport import QMI_Transport
from qmi.instruments.newport.ag_uc8 import Newport_AG_UC8
from qmi.instruments.newport.ag_uc8 import AxisStatus
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.exceptions import QMI_UsageException


# Disable all logging
logging.disable(logging.CRITICAL)


@dataclass
class TestMeta:
    """Test meta data."""

    transport: MagicMock
    transport_str: MagicMock
    name: MagicMock
    super: MagicMock
    instr: Newport_AG_UC8


class TestNewport_AG_UC8(TestCase):
    """Testcase for the Newport_AG_UC8 class."""

    def setUp(self):
        mock_transport = MagicMock(spec=QMI_Transport)
        mock_name = MagicMock()
        mock_transport_str = MagicMock()
        mock_super = MagicMock()

        with patch(
            "qmi.instruments.newport.ag_uc8.create_transport",
            return_value=mock_transport,
        ):
            instr = Newport_AG_UC8(MagicMock(), mock_name, mock_transport_str)

        self._patcher_super = patch("qmi.instruments.newport.ag_uc8.super", mock_super)
        self._patcher_super.start()

        self._meta = TestMeta(
            transport=mock_transport,
            instr=cast(Newport_AG_UC8, instr),
            transport_str=mock_transport_str,
            name=mock_name,
            super=mock_super,
        )

    def tearDown(self):
        self._meta = None
        self._patcher_super.stop()

    def test_init(self):
        """Newport_AG_UC8.__init__(), happy flow"""
        self.assertEqual(self._meta.instr._transport, self._meta.transport)

    def test_open(self):
        """Newport_AG_UC8.open(), happy flow"""

        self._meta.instr._write = MagicMock()
        self._meta.instr._check_error = MagicMock()
        self._meta.instr.open()
        self._meta.transport.open.assert_called_once_with()
        self._meta.super().open.assert_called_once_with()
        self._meta.instr._write.assert_called_once_with("MR")
        self._meta.instr._check_error.assert_called_once_with("MR")

    def test_close(self):
        """Newport_AG_UC8.close(), happy flow"""

        self._meta.instr.close()
        self._meta.transport.close.assert_called_once_with()
        self._meta.super().close.assert_called_once_with()

    def test_write(self):
        """Newport_AG_UC8._write(), happy flow"""

        mock_cmd = "COMMAND"
        self._meta.instr._check_is_open = MagicMock()

        with patch("qmi.instruments.newport.ag_uc8.time.sleep", MagicMock()):
            self._meta.instr._write(mock_cmd)

        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.transport.write.assert_called_once_with(
            mock_cmd.encode("ascii") + b"\r\n"
        )

    def test_ask(self):
        """Newport_AG_UC8._ask(), happy flow"""

        mock_timeout = MagicMock()
        mock_cmd = "COMMAND"
        mock_resp = "RESPONSE\r\n".encode("ascii")

        self._meta.instr._check_is_open = MagicMock()
        self._meta.transport.read_until = MagicMock(return_value=mock_resp)

        rt_val = self._meta.instr._ask(mock_cmd, mock_timeout)

        self._meta.transport.write.assert_called_once_with(
            mock_cmd.encode("ascii") + b"\r\n"
        )
        self._meta.transport.read_until.assert_called_once_with(
            message_terminator=b"\n", timeout=mock_timeout
        )
        self.assertEqual(rt_val, mock_resp.rstrip(b"\r\n").decode("ascii"))
        self._meta.instr._check_is_open.assert_called_once_with()

    def test_get_attribute(self):
        """Newport_AG_UC8._get_attribute(), happy flow"""

        mock_cmd = "DL?"
        mock_timeout = MagicMock()
        mock_attr = 100
        mock_resp = f"DL {mock_attr}"
        self._meta.instr._ask = MagicMock(return_value=mock_resp)

        rt_val = self._meta.instr._get_attribute(mock_cmd, mock_timeout)
        self._meta.instr._ask.assert_called_once_with(mock_cmd, timeout=mock_timeout)
        self.assertEqual(rt_val, mock_attr)

    def test_get_attribute_invalid_response(self):
        """Newport_AG_UC8.get_attribute(), invalid response handling"""

        mock_cmd = "DL?"
        mock_timeout = MagicMock()
        mock_resp = f"INVALID"
        self._meta.instr._ask = MagicMock(return_value=mock_resp)

        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._get_attribute(mock_cmd, mock_timeout)
        self._meta.instr._ask.assert_called_once_with(mock_cmd, timeout=mock_timeout)

    def test_get_attribute_value_error(self):
        """Newport_AG_UC8.get_attribute(), value error handling"""

        mock_cmd = "DL?"
        mock_timeout = MagicMock()
        mock_resp = "DL INVALID"
        self._meta.instr._ask = MagicMock(return_value=mock_resp)

        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._get_attribute(mock_cmd, mock_timeout)
        self._meta.instr._ask.assert_called_once_with(mock_cmd, timeout=mock_timeout)

    def test_get_last_error(self):
        """Newport_AG_UC8.get_last_error(), happy flow"""

        mock_resp = MagicMock()
        self._meta.instr._get_attribute = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_last_error()
        self.assertEqual(rt_val, mock_resp)
        self._meta.instr._get_attribute.assert_called_once_with("TE")

    def test_check_error(self):
        """Newport_AG_UC8._check_error(), happy flow"""
        mock_cmd = MagicMock()
        mock_resp = 0
        self._meta.instr.get_last_error = MagicMock(return_value=mock_resp)
        self._meta.instr._check_error(mock_cmd)
        self._meta.instr.get_last_error.assert_called_once_with()

    def test_check_error_is_error(self):
        """Newport_AG_UC8._check_error(), happy flow"""
        mock_cmd = MagicMock()
        mock_resp = 1
        self._meta.instr.get_last_error = MagicMock(return_value=mock_resp)
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr._check_error(mock_cmd)

    def _test_get_axis_attribute(self, axis):
        mock_attr = MagicMock()
        mock_axis = axis
        mock_timeout = MagicMock()
        mock_resp = MagicMock()
        self._meta.instr._get_attribute = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr._get_axis_attribute(
            mock_attr, mock_axis, mock_timeout
        )
        self._meta.instr._get_attribute.assert_called_once_with(
            f"{mock_axis}{mock_attr}", mock_timeout
        )
        self.assertEqual(rt_val, mock_resp)

    def test_get_axis_attribute(self):
        """Newport_AG_UC8._get_axis_attribute(), happy flow"""
        self._test_get_axis_attribute(1)
        self._test_get_axis_attribute(2)

    def test_get_axis_attribute_invalid_input(self):
        """Newport_AG_UC8._get_axis_attribute(), invalid input handling"""
        with self.assertRaises(QMI_UsageException):
            self._test_get_axis_attribute(0)

    def _test_set_axis_attribute(self, axis):
        mock_attr = MagicMock()
        mock_axis = axis
        mock_value = MagicMock()
        self._meta.instr._write = MagicMock()
        self._meta.instr._check_error = MagicMock()
        self._meta.instr._set_axis_attribute(mock_attr, mock_axis, mock_value)
        self._meta.instr._write.assert_called_once_with(
            f"{mock_axis}{mock_attr}{mock_value}"
        )
        self._meta.instr._check_error.assert_called_once_with(
            f"{mock_axis}{mock_attr}{mock_value}"
        )

    def test_set_axis_attribute(self):
        """Newport_AG_UC8._set_axis_attribute(), happy flow"""
        self._test_set_axis_attribute(1)
        self._test_set_axis_attribute(2)

    def test_set_axis_attribute_invalid_input(self):
        """Newport_AG_UC8._set_axis_attribute(), invalid input handling"""
        with self.assertRaises(QMI_UsageException):
            self._test_set_axis_attribute(0)

    def test_reset(self):
        """Newport_AG_UC8.reset(), happy flow"""
        self._meta.instr._write = MagicMock()
        self._meta.instr._check_error = MagicMock()

        with patch("qmi.instruments.newport.ag_uc8.time.sleep", MagicMock()):
            self._meta.instr.reset()

        self._meta.instr._write.assert_has_calls(
            [
                call("RS"),
                call("MR"),
            ]
        )
        self._meta.instr._check_error.assert_called_once_with("MR")

    def test_get_idn(self):
        """Newport_AG_UC8.get_idn(), happy flow"""
        mock_resp = "MODEL\r\n VERSION \n"
        self._meta.instr._ask = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_idn()

        self.assertEqual(rt_val.vendor, "Newport")
        self.assertEqual(rt_val.model, "MODEL")
        self.assertEqual(rt_val.serial, None)
        self.assertEqual(rt_val.version, "VERSION")

    def test_get_idn_invalid_response(self):
        """Newport_AG_UC8.get_idn(), invalid response handling"""

        mock_resp = ""
        self._meta.instr._ask = MagicMock(return_value=mock_resp)
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.get_idn()

    def _test_select_channel(self, channel):
        mock_channel = channel

        self._meta.instr._write = MagicMock()
        self._meta.instr._check_error = MagicMock()

        with patch("qmi.instruments.newport.ag_uc8.time.sleep", MagicMock()):
            self._meta.instr.select_channel(mock_channel)

        self._meta.instr._write.assert_called_once_with(f"CC{mock_channel}")
        self._meta.instr._check_error.assert_called_once_with("CC")

    def test_select_channel(self):
        """Newport_AG_UC8.select_channel(), happy flow"""
        self._test_select_channel(1)
        self._test_select_channel(2)
        self._test_select_channel(3)
        self._test_select_channel(4)

    def test_select_channel_same_channel(self):
        """Newport_AG_UC8.select_channel(), same channel no write"""
        self._test_select_channel(1)
        with self.assertRaises(AssertionError):
            self._test_select_channel(1)

    def test_select_channel_invalid_input(self):
        """Newport_AG_UC8.select_channel(), invalid input handling"""
        with self.assertRaises(QMI_UsageException):
            self._test_select_channel(0)

    def _test_get_limit_status(self, resp, result):
        mock_channel = MagicMock()
        mock_resp = resp
        self._meta.instr.select_channel = MagicMock()
        self._meta.instr._get_attribute = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_limit_status(mock_channel)
        self._meta.instr.select_channel.assert_called_once_with(mock_channel)
        self._meta.instr._get_attribute.assert_called_once_with("PH")
        self.assertEqual(rt_val, result)

    def test_get_limit_status(self):
        """Newport_AG_UC8.get_limit_status(), happy flow"""
        self._test_get_limit_status(0, (False, False))
        self._test_get_limit_status(1, (True, False))
        self._test_get_limit_status(2, (False, True))
        self._test_get_limit_status(3, (True, True))

    def test_get_limit_status_invalid_response(self):
        """Newport_AG_UC8.get_limit_status(), invalid response handling"""
        with self.assertRaises(QMI_InstrumentException):
            self._test_get_limit_status(4, (False, False))

    def test_get_step_delay(self):
        """Newport_AG_UC8.get_step_delay(), happy flow"""
        mock_resp = MagicMock()
        mock_axis = MagicMock()
        self._meta.instr._get_axis_attribute = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_step_delay(mock_axis)
        self._meta.instr._get_axis_attribute.assert_called_once_with("DL?", mock_axis)
        self.assertEqual(rt_val, mock_resp)

    def test_set_step_delay(self):
        """Newport_AG_UC8.set_step_delay(), happy flow"""
        mock_axis = MagicMock()
        mock_value = MagicMock()
        self._meta.instr._set_axis_attribute = MagicMock()
        self._meta.instr.set_step_delay(mock_axis, mock_value)
        self._meta.instr._set_axis_attribute.assert_called_once_with(
            "DL", mock_axis, mock_value
        )

    def _test_get_step_amplitude(self, direction, attr):
        mock_axis = MagicMock()
        mock_direction = direction
        mock_resp = MagicMock()

        self._meta.instr._get_axis_attribute = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_step_amplitude(mock_axis, mock_direction)
        self.assertEqual(rt_val, mock_resp)
        self._meta.instr._get_axis_attribute.assert_called_once_with(attr, mock_axis)

    def test_get_step_amplitude(self):
        """Newport_AG_UC8.get_step_amplitude(), happy flow"""
        self._test_get_step_amplitude(0, "SU+?")
        self._test_get_step_amplitude(1, "SU-?")

    def test_get_step_amplitude_invalid_input(self):
        """Newport_AG_UC8.get_step_amplitude(), invalid_input"""
        with self.assertRaises(QMI_UsageException):
            self._test_get_step_amplitude(3, "")

    def _test_set_step_amplitude(self, direction, attr):
        mock_axis = MagicMock()
        mock_direction = direction
        mock_resp = MagicMock()
        mock_value = MagicMock()

        self._meta.instr._set_axis_attribute = MagicMock(return_value=mock_resp)
        self._meta.instr.set_step_amplitude(mock_axis, mock_direction, mock_value)
        self._meta.instr._set_axis_attribute.assert_called_once_with(
            attr, mock_axis, mock_value
        )

    def test_set_step_amplitude(self):
        """Newport_AG_UC8.set_step_amplitude(), happy flow"""
        self._test_set_step_amplitude(0, "SU+")
        self._test_set_step_amplitude(1, "SU-")

    def test_set_step_amplitude_invalid_input(self):
        """Newport_AG_UC8.set_step_amplitude(), invalid_input"""
        with self.assertRaises(QMI_UsageException):
            self._test_set_step_amplitude(3, "")

    def test_get_step_count(self):
        """Newport_AG_UC8.get_step_count(), happy flow"""
        mock_axis = MagicMock()
        mock_resp = MagicMock()
        self._meta.instr._get_axis_attribute = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_step_count(mock_axis)
        self._meta.instr._get_axis_attribute.assert_called_once_with("TP", mock_axis)
        self.assertEqual(rt_val, mock_resp)

    def _test_clear_step_count(self, axis):
        mock_axis = axis
        self._meta.instr._write = MagicMock()
        self._meta.instr._check_error = MagicMock()
        self._meta.instr.clear_step_count(mock_axis)
        self._meta.instr._write.assert_called_once_with(f"{mock_axis}ZP")
        self._meta.instr._check_error.assert_called_once_with(f"{mock_axis}ZP")

    def test_clear_step_count(self):
        """Newport_AG_UC8.clear_step_count(), happy flow"""
        self._test_clear_step_count(1)
        self._test_clear_step_count(2)

    def test_clear_step_count_invalid_input(self):
        """Newport_AG_UC8.clear_step_count(), invalid input handling"""
        with self.assertRaises(QMI_UsageException):
            self._test_clear_step_count(3)

    def _test_get_axis_status(self, resp, status):
        mock_axis = MagicMock()
        mock_resp = resp
        self._meta.instr._get_axis_attribute = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.get_axis_status(mock_axis)
        self._meta.instr._get_axis_attribute.assert_called_once_with("TS", mock_axis)
        self.assertEqual(rt_val, status)

    def test_get_axis_status(self):
        """Newport_AG_UC8.get_axis_status(), happy flow"""
        self._test_get_axis_status(0, AxisStatus.READY)
        self._test_get_axis_status(1, AxisStatus.STEPPING)
        self._test_get_axis_status(2, AxisStatus.JOGGING)
        self._test_get_axis_status(3, AxisStatus.MOVING_TO_LIMIT)

    def test_set_jog(self):
        """Newport_AG_UC8.set_jog(), happy flow"""
        mock_channel = MagicMock()
        mock_axis = MagicMock()
        mock_speed = MagicMock()
        self._meta.instr.select_channel = MagicMock()
        self._meta.instr._set_axis_attribute = MagicMock()
        self._meta.instr.jog(mock_channel, mock_axis, mock_speed)
        self._meta.instr.select_channel.assert_called_once_with(mock_channel)
        self._meta.instr._set_axis_attribute.assert_called_once_with(
            "JA", mock_axis, mock_speed
        )

    def test_move_limit(self):
        """Newport_AG_UC8.move_limit(), happy flow"""
        mock_channel = MagicMock()
        mock_axis = MagicMock()
        mock_speed = MagicMock()
        self._meta.instr.select_channel = MagicMock()
        self._meta.instr._set_axis_attribute = MagicMock()
        self._meta.instr.move_limit(mock_channel, mock_axis, mock_speed)
        self._meta.instr.select_channel.assert_called_once_with(mock_channel)
        self._meta.instr._set_axis_attribute.assert_called_once_with(
            "MV", mock_axis, mock_speed
        )

    def test_measure_position(self):
        """Newport_AG_UC8.measure_position(), happy flow"""
        mock_channel = MagicMock()
        mock_axis = MagicMock()
        mock_resp = MagicMock()
        self._meta.instr.select_channel = MagicMock()
        self._meta.instr._get_axis_attribute = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.measure_position(mock_channel, mock_axis)
        self._meta.instr.select_channel.assert_called_once_with(mock_channel)
        self._meta.instr._get_axis_attribute.assert_called_once_with(
            "MA", mock_axis, timeout=self._meta.instr.SLOW_RESPONSE_TIMEOUT
        )
        self.assertEqual(rt_val, mock_resp)

    def test_move_abs(self):
        """Newport_AG_UC8.move_abs(), happy flow"""
        mock_channel = MagicMock()
        mock_axis = MagicMock()
        mock_position = MagicMock()
        mock_resp = MagicMock()
        self._meta.instr.select_channel = MagicMock()
        self._meta.instr._get_axis_attribute = MagicMock(return_value=mock_resp)
        rt_val = self._meta.instr.move_abs(mock_channel, mock_axis, mock_position)
        self._meta.instr.select_channel.assert_called_once_with(mock_channel)
        self._meta.instr._get_axis_attribute.assert_called_once_with(
            f"PA{mock_position}",
            mock_axis,
            timeout=self._meta.instr.SLOW_RESPONSE_TIMEOUT,
        )
        self.assertEqual(rt_val, mock_resp)

    def test_move_rel(self):
        """Newport_AG_UC8.move_rel(), happy flow"""
        mock_channel = MagicMock()
        mock_axis = MagicMock()
        mock_steps = 0
        self._meta.instr.select_channel = MagicMock()
        self._meta.instr._set_axis_attribute = MagicMock()
        self._meta.instr.move_rel(mock_channel, mock_axis, mock_steps)
        self._meta.instr.select_channel.assert_called_once_with(mock_channel)
        self._meta.instr._set_axis_attribute.assert_called_once_with(
            "PR", mock_axis, mock_steps
        )

    def test_move_rel_invalid_input(self):
        """Newport_AG_UC8.move_rel(), invalid input handling"""
        with self.assertRaises(QMI_UsageException):
            self._meta.instr.move_rel(MagicMock(), MagicMock(), 2**31 + 1)

    def _test_stop(self, axis):
        mock_axis = axis
        self._meta.instr._write = MagicMock()
        self._meta.instr.stop(mock_axis)
        self._meta.instr._write.assert_called_once_with(f"{mock_axis}ST")

    def test_stop(self):
        """Newport_AG_UC8.stop(), happy flow"""
        self._test_stop(1)
        self._test_stop(2)

    def test_stop_invalid_input(self):
        """Newport_AG_UC8.stop(), invalid input handling"""
        with self.assertRaises(QMI_UsageException):
            self._test_stop(3)
