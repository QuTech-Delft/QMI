"""Unit test for Wieserlabs FlexDDS NG Dual instrument driver."""

from typing import cast
import unittest
from unittest.mock import MagicMock, call, patch

import qmi
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.transport import QMI_SerialTransport
from qmi.instruments.wieserlabs import OutputChannel, DdsRegister, DcpRegister, Wieserlabs_FlexDdsNg


class TestFlexDDS(unittest.TestCase):

    def setUp(self):
        qmi.start("Test_flex_dds")
        self._transport_mock = MagicMock(spec=QMI_SerialTransport)
        with patch(
                'qmi.instruments.wieserlabs.flexdds.create_transport',
                return_value=self._transport_mock):
            self.instr: Wieserlabs_FlexDdsNg = qmi.make_instrument("instr", Wieserlabs_FlexDdsNg, "transp")
            self.instr = cast(QMI_SerialTransport, self.instr)

    def tearDown(self):
        qmi.stop()

    def _helper_open(self):
        """Open the instrument and check transport interaction."""
        self._transport_mock.read_until.return_value = b"Interactive off\r\n"
        self.instr.open()
        self._transport_mock.open.assert_called_once_with()
        self._transport_mock.open.reset_mock()
        self._transport_mock.discard_read.assert_called_once_with()
        self._transport_mock.discard_read.reset_mock()
        self._transport_mock.write.assert_has_calls([
            call(b"\r"),
            call(b"interactive off\r")
        ])
        self._transport_mock.write.reset_mock()
        self._transport_mock.read_until.assert_called_once_with(
            b"Interactive off\r\n", timeout=Wieserlabs_FlexDdsNg.COMMAND_RESPONSE_TIMEOUT)
        self._transport_mock.read_until.reset_mock()

    def test_open_close(self):
        self._helper_open()
        self.instr.close()
        self._transport_mock.close.assert_called_once_with()

    def test_open_fail_transport(self):
        self._transport_mock.open.side_effect = OSError("failed")
        with self.assertRaises(OSError):
            self.instr.open()
        self._transport_mock.open.assert_called_once_with()
        self._transport_mock.close.assert_not_called()

    def test_open_fail_protocol(self):
        self._transport_mock.read_until.side_effect = QMI_TimeoutException("failed")
        with self.assertRaises(QMI_TimeoutException):
            self.instr.open()
        self._transport_mock.open.assert_called_once_with()
        self._transport_mock.close.assert_called_once_with()

    def test_get_version(self):
        self._helper_open()
        self._transport_mock.read_until.side_effect = [
            b'Version: "dummy,123" (ignored)\r\n',
            b"USER:\r\n"
        ]
        version = self.instr.get_version()
        self.instr.close()
        self._transport_mock.discard_read.assert_called_once_with()
        self._transport_mock.write.assert_called_once_with(b"version\r")
        self.assertEqual(version, "dummy,123")

    def test_get_version_fail(self):
        self._helper_open()
        self._transport_mock.read_until.side_effect = [
            b'Bad response\r\n',
            b"USER:\r\n"
        ]
        with self.assertRaises(QMI_InstrumentException):
            version = self.instr.get_version()
        self.instr.close()

    def test_get_pll_status(self):
        self._helper_open()
        self._transport_mock.read_until.side_effect = [
            b"LMK PLL status: rv=666\n",
            b"  DLD (lock detect): PLL1: *UNLOCK*   PLL2: locked      BOTH: *UNLOCK*\n",
            b"  Holdover . . . . : *ACTIVE*\n",
            b"  DAC. . . . . . . : low\n",
            b"  LOS (signal loss): CLKIN0: *LOST*       CLKIN1: not lost\n",
            b"  CLKIN selected . : CLKIN0: *SELECT*     CLKIN1: (unsel)\n"
        ]
        status = self.instr.get_pll_status()
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"lmkpll\r")
        self.assertFalse(status.pll1_lock)
        self.assertTrue(status.pll2_lock)
        self.assertTrue(status.holdover)
        self.assertTrue(status.clkin0_lost)
        self.assertFalse(status.clkin1_lost)

    def test_dds_reset(self):
        self._helper_open()
        self._transport_mock.read_until.return_value = b"DDS reset OK\r\n"
        self.instr.dds_reset(OutputChannel.OUT0)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"dds 0 reset\r")

    def test_dcp_start(self):
        self._helper_open()
        self.instr.dcp_start(OutputChannel.OUT1)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"dcp 1 start\r")

    def test_dcp_stop(self):
        self._helper_open()
        self.instr.dcp_stop(OutputChannel.BOTH)
        self.instr.close()
        self._transport_mock.write.assert_called_once_with(b"dcp  stop\r")

    def test_dcp_spi_write(self):
        self._helper_open()
        self.instr.dcp_spi_write(OutputChannel.OUT0, DdsRegister.STP0, 0x1234, wait_spi=False, flush=True)
        self.instr.dcp_spi_write(OutputChannel.OUT1, DdsRegister.CFR1, 0x2345, wait_spi=True)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b"dcp 0 spi:STP0=0x1234:c!\r"),
            call(b"dcp 1 spi:CFR1=0x2345:w\r")
        ])

    def test_dcp_register_write(self):
        self._helper_open()
        self.instr.dcp_register_write(OutputChannel.OUT0, DcpRegister.AM_S0, 0x111)
        self.instr.dcp_register_write(OutputChannel.BOTH, DcpRegister.CFG_BNC_A, 0x321, flush=True)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b"dcp 0 wr:AM_S0=0x111\r"),
            call(b"dcp  wr:CFG_BNC_A=0x321!\r")
        ])

    def test_dcp_update(self):
        self._helper_open()
        self.instr.dcp_update(OutputChannel.OUT1, flush=True)
        self.instr.dcp_update(OutputChannel.BOTH)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b"dcp 1 update:u!\r"),
            call(b"dcp  update:u\r")
        ])

    def test_single_tone(self):
        self._helper_open()
        self.instr.set_single_tone(OutputChannel.OUT0, 100.0e6, 0.9, 0.1)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b"dcp 0 spi:CFR1=0x410002:w\r"),
            call(b"dcp 0 spi:CFR2=0x14008c0:w\r"),
            call(b"dcp 0 spi:STP0=0x3999199a1999999a:w\r"),
            call(b"dcp 0 update:u\r"),
            call(b"dcp 0 start\r")
        ])

    def test_single_tone_badparam(self):
        self._helper_open()
        with self.assertRaises(ValueError):
            self.instr.set_single_tone(OutputChannel.OUT0, 800.0e6, 0.9, 0.1)
        with self.assertRaises(ValueError):
            self.instr.set_single_tone(OutputChannel.OUT0, 100.0e6, 1.1, 0.1)
        with self.assertRaises(ValueError):
            self.instr.set_single_tone(OutputChannel.OUT0, 100.0e6, 0.9, -0.1)
        self.instr.close()

    def test_amplitude_modulation(self):
        self._helper_open()
        self.instr.set_amplitude_modulation(OutputChannel.OUT0, 10.0e6, 0.3, 0.25, 0, 0.1, 1.1)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b"dcp 0 spi:CFR1=0x410002:w\r"),
            call(b"dcp 0 spi:CFR2=0x14008d0:w\r"),
            call(b"dcp 0 spi:STP0=0x4000028f5c29:w\r"),
            call(b"dcp 0 wr:AM_O=0x4ccc\r"),
            call(b"dcp 0 wr:AM_S1=0x0\r"),
            call(b"dcp 0 wr:AM_O0=0x199a\r"),
            call(b"dcp 0 wr:AM_S0=0x119a\r"),
            call(b"dcp 0 wr:AM_CFG=0x20000000\r"),
            call(b"dcp 0 update:u\r"),
            call(b"dcp 0 start\r")
        ])

    def test_amplitude_modulation1(self):
        self._helper_open()
        self.instr.set_amplitude_modulation(OutputChannel.OUT1, 10.0e6, 0.3, 0.25, 1, 0.1, 1.1)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b"dcp 1 spi:CFR1=0x410002:w\r"),
            call(b"dcp 1 spi:CFR2=0x14008d0:w\r"),
            call(b"dcp 1 spi:STP0=0x4000028f5c29:w\r"),
            call(b"dcp 1 wr:AM_O=0x4ccc\r"),
            call(b"dcp 1 wr:AM_S0=0x0\r"),
            call(b"dcp 1 wr:AM_O1=0x199a\r"),
            call(b"dcp 1 wr:AM_S1=0x119a\r"),
            call(b"dcp 1 wr:AM_CFG=0x20000000\r"),
            call(b"dcp 1 update:u\r"),
            call(b"dcp 1 start\r")
        ])

    def test_amplitude_modulation_badparam(self):
        self._helper_open()
        with self.assertRaises(ValueError):
            self.instr.set_amplitude_modulation(OutputChannel.OUT1, 800.0e6, 0.3, 0.25, 0, 0.1, 1.1)
        with self.assertRaises(ValueError):
            self.instr.set_amplitude_modulation(OutputChannel.OUT1, 10.0e6, 2.1, 0.25, 0, 0.1, 1.1)
        with self.assertRaises(ValueError):
            self.instr.set_amplitude_modulation(OutputChannel.OUT1, 10.0e6, 0.3, -0.1, 0, 0.1, 1.1)
        with self.assertRaises(ValueError):
            self.instr.set_amplitude_modulation(OutputChannel.OUT1, 10.0e6, 0.3, 0.25, 3, 0.1, 1.1)
        with self.assertRaises(ValueError):
            self.instr.set_amplitude_modulation(OutputChannel.OUT1, 10.0e6, 0.3, 0.25, 0, 0.6, 1.1)
        with self.assertRaises(ValueError):
            self.instr.set_amplitude_modulation(OutputChannel.OUT1, 10.0e6, 0.3, 0.25, 0, 0.1, 31.0)
        self.instr.close()

    def test_frequency_modulation(self):
        self._helper_open()
        self.instr.set_frequency_modulation(OutputChannel.OUT0, 50.0e6, 0.7, 0.0, 1, -0.1, 5.0e6)
        self.instr.close()
        # fm_gain = 9
        self._transport_mock.write.assert_has_calls([
            call(b"dcp 0 spi:CFR1=0x410002:w\r"),
            call(b"dcp 0 spi:CFR2=0x14008d9:w\r"),
            call(b"dcp 0 spi:STP0=0x2ccc00000bcccccd:w\r"),
            call(b"dcp 0 spi:FTW=0xbcccccd:w\r"),
            call(b"dcp 0 wr:AM_O=0x8000\r"),
            call(b"dcp 0 wr:AM_S0=0x0\r"),
            call(b"dcp 0 wr:AM_O1=0x3e666\r"),
            call(b"dcp 0 wr:AM_S1=0xa3d\r"),
            call(b"dcp 0 wr:AM_CFG=0x20000002\r"),
            call(b"dcp 0 update:u\r"),
            call(b"dcp 0 start\r")
        ])

    def test_frequency_modulation1(self):
        self._helper_open()
        self.instr.set_frequency_modulation(OutputChannel.OUT1, 3.0e6, 0.7, 0.0, 0, -0.1, 5.0e6)
        self.instr.close()
        # fm_gain = 9
        self._transport_mock.write.assert_has_calls([
            call(b"dcp 1 spi:CFR1=0x410002:w\r"),
            call(b"dcp 1 spi:CFR2=0x14008d9:w\r"),
            call(b"dcp 1 spi:STP0=0x2ccc0000000001a6:w\r"),
            call(b"dcp 1 spi:FTW=0x1a6:w\r"),
            call(b"dcp 1 wr:AM_O=0x624d\r"),
            call(b"dcp 1 wr:AM_S1=0x0\r"),
            call(b"dcp 1 wr:AM_O0=0x3e666\r"),
            call(b"dcp 1 wr:AM_S0=0xa3d\r"),
            call(b"dcp 1 wr:AM_CFG=0x20000002\r"),
            call(b"dcp 1 update:u\r"),
            call(b"dcp 1 start\r")
        ])

    def test_frequency_modulation_badparam(self):
        self._helper_open()
        with self.assertRaises(ValueError):
            self.instr.set_frequency_modulation(OutputChannel.OUT0, 500.0e6, 0.7, 0.0, 1, -0.1, 5.0e6)
        with self.assertRaises(ValueError):
            self.instr.set_frequency_modulation(OutputChannel.OUT0, 50.0e6, 1.1, 0.0, 1, -0.1, 5.0e6)
        with self.assertRaises(ValueError):
            self.instr.set_frequency_modulation(OutputChannel.OUT0, 50.0e6, 0.7, 1.1, 1, -0.1, 5.0e6)
        with self.assertRaises(ValueError):
            self.instr.set_frequency_modulation(OutputChannel.OUT0, 50.0e6, 0.7, 0.0, 3, -0.1, 5.0e6)
        with self.assertRaises(ValueError):
            self.instr.set_frequency_modulation(OutputChannel.OUT0, 50.0e6, 0.7, 0.0, 1, -0.6, 5.0e6)
        with self.assertRaises(ValueError):
            self.instr.set_frequency_modulation(OutputChannel.OUT0, 50.0e6, 0.7, 0.0, 1, -0.1, 600.0e6)
        self.instr.close()

    def test_digital_modulation(self):
        self._helper_open()
        self.instr.set_digital_modulation(OutputChannel.OUT0, 400.0e6, 0.7, 0.0, 1, False)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b"dcp 0 wr:CFG_BNC_B=0x0\r"),
            call(b"dcp 0 wr:CFG_OSK=0x408\r"),
            call(b"dcp 0 spi:CFR1=0xc10202:w\r"),
            call(b"dcp 0 spi:CFR2=0x14008c0:w\r"),
            call(b"dcp 0 spi:STP0=0x2ccc000066666666:w\r"),
            call(b"dcp 0 spi:ASF=0xb330:w\r"),
            call(b"dcp 0 update:u\r"),
            call(b"dcp 0 start\r")
        ])

    def test_phase_modulation(self):
        self._helper_open()
        self.instr.set_phase_modulation(OutputChannel.OUT0, 10.0e6, 0.7, 0, 0.1, 1.1)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b"dcp 0 spi:CFR1=0x410002:w\r"),
            call(b"dcp 0 spi:CFR2=0x14008d0:w\r"),
            call(b"dcp 0 spi:STP0=0x2ccc0000028f5c29:w\r"),
            call(b"dcp 0 wr:AM_O=0x0\r"),
            call(b"dcp 0 wr:AM_S1=0x0\r"),
            call(b"dcp 0 wr:AM_O0=0x199a\r"),
            call(b"dcp 0 wr:AM_S0=0x119a\r"),
            call(b"dcp 0 wr:AM_CFG=0x20000001\r"),
            call(b"dcp 0 update:u\r"),
            call(b"dcp 0 start\r")
        ])

    def test_phase_modulation1(self):
        self._helper_open()
        self.instr.set_phase_modulation(OutputChannel.OUT1, 10.0e6, 0.7, 1, 0.1, 1.1)
        self.instr.close()
        self._transport_mock.write.assert_has_calls([
            call(b"dcp 1 spi:CFR1=0x410002:w\r"),
            call(b"dcp 1 spi:CFR2=0x14008d0:w\r"),
            call(b"dcp 1 spi:STP0=0x2ccc0000028f5c29:w\r"),
            call(b"dcp 1 wr:AM_O=0x0\r"),
            call(b"dcp 1 wr:AM_S0=0x0\r"),
            call(b"dcp 1 wr:AM_O1=0x199a\r"),
            call(b"dcp 1 wr:AM_S1=0x119a\r"),
            call(b"dcp 1 wr:AM_CFG=0x20000001\r"),
            call(b"dcp 1 update:u\r"),
            call(b"dcp 1 start\r")
        ])


if __name__ == '__main__':
    unittest.main()
