""" Testcase of the SDS1202X-E Siglent Oscilloscope. """
import unittest
from unittest.mock import call, patch
import numpy as np

import qmi
from qmi.instruments.siglent import Siglent_Sds1202xE, CommHeader, TriggerCondition
from qmi.core.transport import QMI_TcpTransport
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException


class TestSDS1202XE(unittest.TestCase):
    """ Testcase of the TestSDS1202XE oscilloscope """

    def setUp(self):
        qmi.start("TestSiglentSDS1202X-E")
        # Add patches
        patcher = patch('qmi.instruments.siglent.sds1202xe.create_transport', spec=QMI_TcpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        patcher = patch('qmi.instruments.siglent.sds1202xe.ScpiProtocol', autospec=True)
        self._scpi_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.scope: Siglent_Sds1202xE = qmi.make_instrument("SDS1202XE", Siglent_Sds1202xE, "")
        self.scope.open()

    def tearDown(self):
        self.scope.close()
        qmi.stop()

    def test_channel_exception(self):
        with self.assertRaises(ValueError):
            _ = self.scope.trace_dump(-1)
        with self.assertRaises(ValueError):
            _ = self.scope.trace_dump(6)

    def test_get_id(self):
        """ Test case for `get_id(...)` function. """
        # arrange
        expected_id_string = "test_string"
        expected_calls = [call.write('chdr off'), call.ask("*IDN?")]
        self._scpi_mock.ask.return_value = expected_id_string
        # act
        actual_val = self.scope.get_id()
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)
        self.assertEqual(actual_val, expected_id_string)

    def test_set_comm_header(self):
        """ Test case for `set_comm_header(...) method. """
        expected_scpi_calls = [
            [call.write("chdr long")],
            [call.write("chdr short")],
            [call.write("chdr off")],
        ]
        for i, header in enumerate(CommHeader):
            self._scpi_mock.reset_mock()
            with self.subTest(i=header.value):
                self.scope.set_comm_header(header)
                self.assertEqual(self._scpi_mock.method_calls, expected_scpi_calls[i])

    def test_get_voltage_per_division(self):
        """ Test case for `get_voltage_per_division(...)` method. """
        # arrange
        expected_vdiv = 1.0
        expected_calls = [call.write('chdr off'), call.ask("c1:vdiv?")]
        self._scpi_mock.ask.return_value = str(expected_vdiv)
        # act
        actual_val = self.scope.get_voltage_per_division(1)
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)
        self.assertEqual(actual_val, expected_vdiv)

    def test_get_voltage_per_division_exceptions(self):
        """ Test case for QMI_InstrumentException in `get_voltage_per_division(...)`"""
        # arrange
        self._scpi_mock.ask.side_effect = "Error"
        # act & assert
        with self.assertRaises(QMI_InstrumentException):
            _ = self.scope.get_voltage_per_division(1)

    def test_set_voltage_per_division(self):
        """ Test case for `set_voltage_per_division(...)` method. """
        # arrange
        expected_vdiv = 1.0
        expected_calls = [call.write('chdr off'), call.write(f"c1:vdiv {expected_vdiv}")]
        # act
        self.scope.set_voltage_per_division(1, expected_vdiv)
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)

    def test_set_voltage_per_division_exceptions(self):
        """ Test case for ValueError in `set_voltage_per_division(...)`"""
        # arrange
        out_of_range_vdivs = [100E-6, 20.0]
        # act & assert
        for vdiv in out_of_range_vdivs:
            with self.assertRaises(ValueError):
                self.scope.set_voltage_per_division(1, vdiv)

    def test_get_voltage_offset(self):
        """ Test case for `get_voltage_offset(...)` method. """
        # arrange
        expected_ofst = 1.0
        expected_calls = [call.write('chdr off'), call.ask("c1:ofst?")]
        self._scpi_mock.ask.return_value = str(expected_ofst)
        # act
        actual_val = self.scope.get_voltage_offset(1)
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)
        self.assertEqual(actual_val, expected_ofst)

    def test_get_voltage_offset_exceptions(self):
        """ Test case for QMI_InstrumentException in `get_voltage_offset(...)`"""
        # arrange
        self._scpi_mock.ask.side_effect = "Error"
        # act & assert
        with self.assertRaises(QMI_InstrumentException):
            self.scope.get_voltage_offset(1)

    def test_set_voltage_offset(self):
        """ Test case for `set_voltage_offset(...)` method. """
        # arrange
        expected_ofst = 1.0
        channel = 3
        expected_calls = [call.write('chdr off'), call.write(f"c3:ofst {expected_ofst}")]
        # act
        self.scope.set_voltage_offset(channel, expected_ofst)
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)

    def test_get_time_per_division(self):
        """ Test case for `get_time_per_division(...)` method. """
        # arrange
        expected_tdiv = 1.0
        expected_calls = [call.write('chdr off'), call.ask("tdiv?")]
        self._scpi_mock.ask.return_value = str(expected_tdiv)
        # act
        actual_val = self.scope.get_time_per_division()
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)
        self.assertEqual(actual_val, expected_tdiv)

    def test_get_time_per_division_exceptions(self):
        """ Test case for QMI_InstrumentException in `get_time_per_division(...)`"""
        # arrange
        self._scpi_mock.ask.side_effect = "Error"
        # act & assert
        with self.assertRaises(QMI_InstrumentException):
            self.scope.get_time_per_division()

    def test_set_time_per_division(self):
        """ Test case for `set_time_per_division(...)` method. """
        # arrange
        expected_tdivs = [1, 20, 50, 200]
        expected_units = ["s", "ms", "us", "ns"]
        expected_calls = [call.write('chdr off'),] + \
                         [call.write(f"tdiv {expected_tdivs[e]}{expected_units[e]}") for e in range(4)]
        # act
        for s in range(4):
            self.scope.set_time_per_division(expected_tdivs[s], expected_units[s])

        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)

    def test_set_time_per_division_exceptions(self):
        """ Test case for ValueError in `set_time_per_division(...)`"""
        # arrange
        unexpected_tdiv = [1, 3, 200]
        unexpected_unit = ["ps", "ms", "s"]
        # act & assert
        for u in range(3):
            with self.assertRaises(ValueError):
                self.scope.set_time_per_division(unexpected_tdiv[u], unexpected_unit[u])

    def test_get_sample_rate(self):
        """ Test case for `get_sample_rate(...)` method. """
        # arrange
        expected_sara = 1.0
        expected_calls = [call.write('chdr off'), call.ask("sara?")]
        self._scpi_mock.ask.return_value = str(expected_sara)
        # act
        actual_val = self.scope.get_sample_rate()
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)
        self.assertEqual(actual_val, expected_sara)

    def test_get_sample_rate_exceptions(self):
        """ Test case for QMI_InstrumentException in `get_sample_rate(...)`"""
        # arrange
        self._scpi_mock.ask.side_effect = "Error"
        # act & assert
        with self.assertRaises(QMI_InstrumentException):
            _ = self.scope.get_sample_rate()

    def test_get_trigger_coupling(self):
        """ Test case for `get_trigger_coupling(...)` method. """
        # arrange
        expected_channel = 5
        expected_trcp = "2.0"
        expected_calls = [call.write('chdr off'), call.ask("ex5:trcp?")]
        self._scpi_mock.ask.return_value = expected_trcp
        # act
        actual_val = self.scope.get_trigger_coupling(expected_channel)
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)
        self.assertEqual(actual_val, expected_trcp)

    def test_set_trigger_coupling(self):
        """ Test case for `set_trigger_coupling(...)` method. """
        # arrange
        expected_trcps = ["ac", "dc", "hfrej", "lfrej"]
        channel = 5
        expected_calls = [call.write('chdr off'),] + [call.write(f"ex5:trcp {e}") for e in expected_trcps]
        # act
        for expected_trcp in expected_trcps:
            self.scope.set_trigger_coupling(channel, expected_trcp)

        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)

    def test_set_trigger_coupling_exception(self):
        """ Test case for ValueError in `set_trigger_coupling(...) method."""
        # arrange
        unexpected_trcp = "ac/dc"
        # act
        with self.assertRaises(ValueError) as exc:
            self.scope.set_trigger_coupling(3, unexpected_trcp)

        self.assertIn(unexpected_trcp, str(exc.exception))

    def test_get_trigger_level(self):
        """ Test case for `get_trigger_level(...)` method. """
        # arrange
        expected_channel = 4
        expected_trlv = 5.5
        expected_calls = [call.write('chdr off'), call.ask("c4:trlv?")]
        self._scpi_mock.ask.return_value = str(expected_trlv)
        # act
        actual_val = self.scope.get_trigger_level(expected_channel)
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)
        self.assertEqual(actual_val, expected_trlv)

    def test_set_trigger_level_external(self):
        """ Test case for `set_trigger_level(...)` method for an external channel. """
        # arrange
        expected_trlv = 2.0
        channel = 5
        expected_calls = [call.write('chdr off'), call.write(f"ex5:trlv {expected_trlv}")]
        # act
        self.scope.set_trigger_level(channel, expected_trlv)

        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)

    def test_set_trigger_level_internal(self):
        """ Test case for `set_trigger_level(...)` method for an internal channel. """
        # arrange
        expected_vdiv = "1.0"
        expected_trlv = 2.0
        channel = 4
        expected_calls = [call.write('chdr off'), call.write(f"c4:trlv {expected_trlv}")]
        self._scpi_mock.ask.return_value = expected_vdiv
        # act
        self.scope.set_trigger_level(channel, expected_trlv)

        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)

    def test_get_trigger_mode(self):
        """ Test case for `get_trigger_mode(...)` method. """
        # arrange
        expected_trmd = "AUTO"
        expected_calls = [call.write('chdr off'), call.ask("trmd?")]
        self._scpi_mock.ask.return_value = expected_trmd
        # act
        actual_val = self.scope.get_trigger_mode()
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)
        self.assertEqual(actual_val, expected_trmd)

    def test_set_trigger_mode(self):
        """ Test case for `set_trigger_mode(...)` method. """
        # arrange
        expected_trmds = ["auto", "norm", "single", "STOP"]
        expected_calls = [call.write('chdr off'),] + [call.write(f"trmd {e}") for e in expected_trmds]
        # act
        for expected_trmd in expected_trmds:
            self.scope.set_trigger_mode(expected_trmd)

        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)

    def test_set_trigger_mode_exception(self):
        """ Test case for ValueError in `set_trigger_mode(...) method."""
        # arrange
        unexpected_trmd = "DOUBLE"
        # act
        with self.assertRaises(ValueError) as exc:
            self.scope.set_trigger_mode(unexpected_trmd)

        self.assertIn(unexpected_trmd, str(exc.exception))

    def test_get_trigger_select(self):
        """ Test case for `get_trigger_select(...)` method. """
        # arrange
        trmd1 = "trig_type,source,hold_type,hold_value,hold_value2"
        expected_trmd1 = TriggerCondition("trig_type", "source", "hold_type", "hold_value", "hold_value2")
        expected_calls = [call.write('chdr off'), call.ask("trse?")]
        self._scpi_mock.ask.return_value = trmd1
        # act
        actual_val1 = self.scope.get_trigger_select()
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)
        self.assertEqual(actual_val1, expected_trmd1)

    def test_get_trigger_slope(self):
        """ Test case for `get_trigger_slope(...)` method. """
        # arrange
        expected_trsl = "window"
        expected_calls = [call.write('chdr off'), call.ask("c1:trsl?")]
        self._scpi_mock.ask.return_value = expected_trsl
        # act
        actual_val = self.scope.get_trigger_slope(1)
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)
        self.assertEqual(actual_val, expected_trsl)

    def test_set_trigger_slope(self):
        """ Test case for `set_trigger_slope(...)` method. """
        # arrange
        expected_trsls = ["neg", "POS", "window"]
        channels = [3, 2, 1]
        expected_calls = [call.write('chdr off'),] + \
                         [call.write(f"c{c}:trsl {e}") for c, e in zip(channels, expected_trsls)]
        # act
        for channel, expected_trsl in zip(channels, expected_trsls):
            self.scope.set_trigger_slope(channel, expected_trsl)

        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)

    def test_set_trigger_slope_exception(self):
        """ Test case for ValueError in `set_trigger_slope(...) method."""
        # arrange
        unexpected_trsl = "neutral"
        # act
        with self.assertRaises(ValueError) as exc:
            self.scope.set_trigger_slope(0, unexpected_trsl)

        self.assertIn(unexpected_trsl, str(exc.exception))

    def test_arm_trigger(self):
        """Test for `arm_trigger()` method."""
        # arrange
        expected_calls = [call.write('chdr off'), call.write("arm")]
        # act
        self.scope.arm_trigger()
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)

    def test_stop_acquisition(self):
        """Test for `stop_acquisition()` method."""
        # arrange
        expected_calls = [call.write('chdr off'), call.write("stop")]
        # act
        self.scope.stop_acquisition()
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)

    def test_get_trigger_state(self):
        """Test how to get trigger state with `get_trigger_state()` method."""
        # arrange
        expected_state = 0
        expected_calls = [call.write('chdr off'), call.ask("inr?")]
        self._scpi_mock.ask.return_value = str(expected_state)
        # act
        state = self.scope.get_trigger_state()
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls)
        self.assertEqual(state, expected_state)

    def test_get_trigger_state_exception(self):
        """Test getting trigger state with `get_trigger_state()` method throws exception."""
        # arrange
        expected_state = "zero"
        self._scpi_mock.ask.return_value = expected_state
        # act
        with self.assertRaises(QMI_InstrumentException):
            self.scope.get_trigger_state()

    def test_screen_dump(self):
        """ Test case for `screen_dump(...)` function. """
        # arrange
        expected_dump = bytes(768066)  # replace with random string
        expected_calls_scpi = [call.write('chdr off'), call.write("SCDP")]
        expected_calls_transport = [
            call.open,
            call.read(len(expected_dump), 2.0),  # can you make an argument a don't care?
            call.read(1, 2.0)
        ]
        self._transport_mock.read.side_effect = [expected_dump, b'\n']
        # act
        actual_dump = self.scope.screen_dump()
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls_scpi)
        self.assertEqual(self._transport_mock.method_calls, expected_calls_transport)
        self.assertEqual(actual_dump, expected_dump)

    def test_screen_dump_exception(self):
        """ Test case for `screen_dump(...)` exception handling. """
        # arrange
        self._transport_mock.read.side_effect = [bytes(768066), b'\x00']
        # act
        with self.assertRaises(QMI_InstrumentException):
            _ = self.scope.screen_dump()

    def test_get_waveform_channel_1(self):
        """ Test case for `get_waveform(...)` function. """
        # arrange
        expected_dump = b'Hello World!'  # replace with random string
        expected_calls_scpi = [
            call.write('chdr off'),
            call.write("c1:wf? dat2"),
            call.read_binary_data()
        ]
        expected_calls_transport = [
            call.open,
            call.read(5, 2.0),
            call.read(1, 2.0)
        ]
        self._transport_mock.read.side_effect = [b"DAT2,", b'\n']
        self._scpi_mock.read_binary_data.return_value = expected_dump
        # act
        actual_dump = self.scope.get_waveform(1)
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls_scpi)
        self.assertEqual(self._transport_mock.method_calls, expected_calls_transport)
        self.assertEqual(actual_dump, expected_dump)

    def test_get_waveform_channel_digital(self):
        """ Test case for `get_waveform(...)` function. """
        # arrange
        expected_dump = b'Hello World!'  # replace with random string
        expected_calls_scpi = [
            call.write('chdr off'),
            call.write("d1:wf? dat2"),
            call.read_binary_data()
        ]
        expected_calls_transport = [
            call.open,
            call.read(5, 2.0),
            call.read(1, 2.0)
        ]
        self._transport_mock.read.side_effect = [b"DAT2,", b'\n']
        self._scpi_mock.read_binary_data.return_value = expected_dump
        # act
        actual_dump = self.scope.get_waveform("d1")
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls_scpi)
        self.assertEqual(self._transport_mock.method_calls, expected_calls_transport)
        self.assertEqual(actual_dump, expected_dump)

    def test_get_waveform_exceptions_invalid_response(self):
        """ Test case for `get_waveform(...)` exception handling. """
        # arrange
        side_effects = {
            "invalid_hdr": [b'\x00'],
            "invalid_trm": [b"DAT2,", b'\x00']
        }
        # act
        for k, v in side_effects.items():
            with self.subTest(i=k):
                self._transport_mock.read.side_effect = v
                with self.assertRaises(QMI_InstrumentException):
                    self.scope.get_waveform(1)

    def test_get_waveform_exceptions_invalid_channel(self):
        """ Test case for `get_waveform(...)` exception handling. """
        # arrange
        side_effects = {
            "invalid_hdr": [b'\x00'],
            "invalid_trm": [b"DAT2,", b'\x00']
        }
        # act
        for k, v in side_effects.items():
            with self.subTest(i=k):
                self._transport_mock.read.side_effect = v
                with self.assertRaises(QMI_UsageException):
                    self.scope.get_waveform("d100")

    def test_get_waveform_exceptions_invalid_channel_type(self):
        """ Test case for `get_waveform(...)` exception handling. """
        # arrange
        side_effects = {
            "invalid_hdr": [b'\x00'],
            "invalid_trm": [b"DAT2,", b'\x00']
        }
        # act
        for k, v in side_effects.items():
            with self.subTest(i=k):
                self._transport_mock.read.side_effect = v
                with self.assertRaises(QMI_UsageException):
                    self.scope.get_waveform(1.1)

    def test_trace_dump(self):
        """ Test case for `trace_dump(...)` function. This test mainly checks the logic of the conversion from 
            byte data to actual time and voltage data which are returned as np.ndarrays. 
            Logic from datasheet are as follows:
                - voltage value (V) = code value *(vdiv /25) - voffset
                - time value(S) = - index*(tdiv*grid/2).
        """
        # arrange
        channel = 1
        expected_trace = (
            np.arange(-7.0, 8.0, 1.0),
            np.full((15,), 2.0)
        )
        expected_calls_scpi = [
            call.write('chdr off'),
            call.write("chdr off"),
            call.ask(f"c{channel}:vdiv?"),
            call.ask(f"c{channel}:ofst?"),
            call.ask("tdiv?"),
            call.ask("sara?"),
            call.write(f"c{channel}:wf? dat2"),
            call.read_binary_data(),
        ]
        self._scpi_mock.ask.side_effect = ['1.0', '-1.0', '1.0', '1.0']
        self._scpi_mock.read_binary_data.return_value = bytes([25 for _ in range(15)])
        expected_calls_transport = [
            call.open,
            call.discard_read(),
            call.read(5, 2.0),
            call.read(1, 2.0),
        ]
        self._transport_mock.read.side_effect = [b'DAT2,', b'\n']
        # act
        actual_dump = self.scope.trace_dump(channel)
        # assert
        self.assertEqual(self._scpi_mock.method_calls, expected_calls_scpi)
        self.assertEqual(self._transport_mock.method_calls, expected_calls_transport)
        self.assertEqual(actual_dump[0].tolist(), expected_trace[0].tolist())
        self.assertEqual(actual_dump[1].tolist(), expected_trace[1].tolist())


if __name__ == '__main__':
    unittest.main()
