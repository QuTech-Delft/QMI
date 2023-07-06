"""Test for the Tektronix FCA3000 driver."""
import struct

from math import isnan

from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch
from unittest.mock import call

from typing import cast

from dataclasses import dataclass


from qmi.core.transport import QMI_Transport
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.instruments.tektronix.fca3000 import Tektronix_FCA3000
from qmi.core.exceptions import QMI_InstrumentException


@dataclass
class TestMeta:
    """Test meta data."""

    transport: MagicMock
    transport_str: MagicMock
    name: MagicMock
    scpi: MagicMock
    super: MagicMock
    instr: Tektronix_FCA3000


class TestFCA3000(TestCase):
    """Testcase for the Tektronix_FCA3000 class."""

    def setUp(self):
        mock_transport = MagicMock(spec=QMI_Transport)
        mock_name = MagicMock()
        mock_transport_str = MagicMock()
        mock_scpi = MagicMock(spec=ScpiProtocol)
        mock_super = MagicMock()

        with patch(
            "qmi.instruments.tektronix.fca3000.create_transport",
            return_value=mock_transport,
        ), patch("qmi.instruments.tektronix.fca3000.ScpiProtocol", mock_scpi):
            instr = Tektronix_FCA3000(MagicMock(), mock_name, mock_transport_str)

        self._patcher_super = patch(
            "qmi.instruments.tektronix.fca3000.super", mock_super
        )
        self._patcher_super.start()

        self._meta = TestMeta(
            transport=mock_transport,
            instr=cast(Tektronix_FCA3000, instr),
            transport_str=mock_transport_str,
            name=mock_name,
            scpi=mock_scpi(mock_transport),
            super=mock_super,
        )

    def tearDown(self):
        self._meta = None
        self._patcher_super.stop()

    def test_init(self):
        """Tektronix_FCA3000.__init__(), happy flow."""
        self.assertEqual(self._meta.instr._transport, self._meta.transport)
        self.assertEqual(self._meta.instr._scpi_transport, self._meta.scpi)

    def test_open(self):
        """Tektronix_FCA3000.open(), happy flow."""
        self._meta.instr.open()
        self._meta.transport.open.assert_called_once_with()
        self._meta.super().open.assert_called_once_with()

    def test_close(self):
        """Tektronix_FCA3000.close(), happy flow."""
        self._meta.instr.close()
        self._meta.super().close.assert_called_once_with()
        self._meta.transport.close.assert_called_once_with()

    def test_reset(self):
        """Tektronix_FCA3000.reset(), happy flow."""
        self._meta.instr.reset()
        self._meta.scpi.write.assert_called_once_with("*RST")
        self._meta.scpi.ask.assert_called_once_with("*OPC?")

    def test_get_idn(self):
        """Tektronix_FCA3000.get_idn(), happy flow."""
        self._meta.scpi.ask = MagicMock(return_value="VENDOR,MODEL,SERIAL,VERSION")
        rt_val = self._meta.instr.get_idn()
        self._meta.scpi.ask.assert_called_once_with("*IDN?")
        self.assertEqual(rt_val.vendor, "VENDOR")
        self.assertEqual(rt_val.model, "MODEL")
        self.assertEqual(rt_val.serial, "SERIAL")
        self.assertEqual(rt_val.version, "VERSION")

    def test_get_idn_invalid_response(self):
        """Tektronix_FCA3000.get_idn(), invalid response."""
        self._meta.scpi.ask = MagicMock(return_value="")
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.get_idn()
        self._meta.scpi.ask.assert_called_once_with("*IDN?")

    def test_get_errors(self):
        """Tektronix_FCA3000.get_errors(), happy flow."""
        self._meta.scpi.ask = MagicMock(side_effect=["1,", "2,", "0,"])
        rt_val = self._meta.instr.get_errors()
        self._meta.scpi.ask.assert_has_calls(
            [call("SYST:ERR?"), call("SYST:ERR?"), call("SYST:ERR?")]
        )
        self.assertEqual(len(rt_val), 2)
        self.assertEqual(rt_val[0], "1,")
        self.assertEqual(rt_val[1], "2,")

    def test_measure_frequency(self):
        """Tektronix_FCA3000.measure_frequency(), happy flow."""
        mock_channel = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value="0.003    ")
        rt_val = self._meta.instr.measure_frequency(mock_channel)
        self._meta.scpi.ask.assert_called_once_with(
            "MEAS:FREQ? (@{})".format(mock_channel)
        )
        self.assertEqual(rt_val, 0.003)

    def test_configure_frequency(self):
        """Tektronix_FCA3000.configure_frequency(), happy flow."""
        mock_channel = MagicMock()
        mock_aperture = 0.01
        mock_trigger_level = 0.02
        mock_timestamp = MagicMock()
        self._meta.instr.configure_frequency(
            channel=mock_channel,
            aperture=mock_aperture,
            trigger_level=mock_trigger_level,
            timestamp=mock_timestamp,
        )
        self._meta.scpi.write.assert_has_calls(
            [
                call("CONF:FREQ (@{})".format(mock_channel)),
                call("ACQ:APER {:.6g}".format(mock_aperture)),
                call("INP{}:LEV:AUTO 0".format(mock_channel)),
                call("INP{}:LEV {:.6g}".format(mock_channel, mock_trigger_level)),
                call("FORM:TINF {}".format(int(mock_timestamp))),
            ]
        )

    def test_read_values(self):
        """Tektronix_FCA3000.read_value(), happy flow."""
        self._meta.scpi.ask = MagicMock(return_value="0.001,0.002")
        rt_val = self._meta.instr.read_value()
        self._meta.scpi.ask.assert_called_once_with("READ?")
        self.assertEqual(rt_val, 0.001)

    def test_read_timestamped_value(self):
        """Tektronix_FCA3000.read_timestamped_value(), happy flow."""
        self._meta.scpi.ask = MagicMock(return_value="0.001,0.002")
        rt_val = self._meta.instr.read_timestamped_value()
        self._meta.scpi.ask.assert_called_once_with("READ?")
        self.assertEqual(rt_val[0], 0.002)
        self.assertEqual(rt_val[1], 0.001)

    def test_read_timestamped_value_invalid_response(self):
        """Tektronix_FCA3000.read_timestamped_value(), happy flow."""
        self._meta.scpi.ask = MagicMock(return_value="")
        with self.assertRaises(QMI_InstrumentException):
            self._meta.instr.read_timestamped_value()
        self._meta.scpi.ask.assert_called_once_with("READ?")

    def test_set_talk_only_enable(self):
        """Tektronix_FCA3000.set_talk_only(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.instr.set_talk_only(True)
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.transport.read_until_timeout.assert_called_once_with(
            nbytes=16384, timeout=1.0
        )
        self._meta.scpi.ask.assert_called_once_with("*OPC?")
        self._meta.scpi.write.assert_has_calls(
            [
                call("++ifc"),
                call("FORM PACK"),
                call("DISP:ENAB 0"),
                call("INIT:CONT 1"),
                call("SYST:TALK 1"),
            ]
        )
        self._meta.scpi.read_binary_data.assert_called_once_with()

    def test_set_talk_only_disable(self):
        """Tektronix_FCA3000.set_talk_only(), happy flow."""
        self._meta.instr._check_is_open = MagicMock()
        self._meta.instr.set_talk_only(False)
        self._meta.instr._check_is_open.assert_called_once_with()
        self._meta.transport.read_until_timeout.assert_called_once_with(
            nbytes=16384, timeout=1.0
        )
        self._meta.scpi.ask.assert_called_once_with("*OPC?")
        self._meta.scpi.write.assert_called_once_with("++ifc")

    def test_get_value_talk_only(self):
        """Tektronix_FCA3000.get_value_talk_only(), happy flow."""
        mock_timestamp = 100
        mock_value = 200
        self._meta.scpi.read_binary_data = MagicMock(
            return_value=struct.pack(">dq", mock_value, mock_timestamp)
        )
        rt_val = self._meta.instr.get_value_talk_only()
        self.assertEqual(
            rt_val[0], mock_timestamp * 1.0e-12
        )  # timestamp conversion in function
        self.assertEqual(rt_val[1], mock_value)

    def test_get_value_talk_only_no_timestamp(self):
        """Tektronix_FCA3000.get_value_talk_only(), happy flow."""
        mock_value = 200
        self._meta.scpi.read_binary_data = MagicMock(
            return_value=struct.pack(">d", mock_value)
        )
        rt_val = self._meta.instr.get_value_talk_only()
        self.assertTrue(isnan(rt_val[0]))
        self.assertEqual(rt_val[1], mock_value)

    def test_get_trigger_level(self):
        """Tektronix_FCA3000.get_trigger_level(), happy flow."""
        mock_channel = MagicMock()
        self._meta.scpi.ask = MagicMock(return_value="0.001")
        rt_val = self._meta.instr.get_trigger_level(mock_channel)
        self._meta.scpi.ask.assert_called_once_with("INP{}:LEV?".format(mock_channel))
        self.assertEqual(rt_val, 0.001)

    def test_set_display_enabled(self):
        """Tektronix_FCA3000.set_display_enabled(), happy flow."""
        mock_enable = MagicMock()
        self._meta.instr.set_display_enabled(mock_enable)
        self._meta.scpi.write.assert_called_once_with(
            "DISP:ENAB {}".format(int(mock_enable))
        )

    def test_set_initiate_continuous(self):
        """Tektronix_FCA3000.set_initiate_continuous(), happy flow."""
        mock_enable = MagicMock()
        self._meta.instr.set_initiate_continuous(mock_enable)
        self._meta.scpi.write.assert_called_once_with(
            "INIT:CONT {}".format(int(mock_enable))
        )
