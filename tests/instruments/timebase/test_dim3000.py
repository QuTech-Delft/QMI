from dataclasses import asdict
import unittest
from unittest.mock import patch, ANY, create_autospec, PropertyMock

import qmi
from qmi.instruments.timebase import TimeBase_Dim3000
from qmi.instruments.timebase.dim3000 import DIM3000SweepMode, DIM3000FMDeviation
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_InstrumentIdentification
from qmi.core.transport import QMI_Transport


class TestDim3000(unittest.TestCase):

    def setUp(self) -> None:
        self.maxDiff = None

        qmi.start("TestDim3000", init_logging=False)

        # Create mocks
        self._transport_mock = create_autospec(QMI_Transport)

        # Add patches
        patcher = patch('qmi.instruments.timebase.dim3000.create_transport', return_value=self._transport_mock)
        self._transport_factory = patcher.start()
        self.addCleanup(patcher.stop)

        self.instr: TimeBase_Dim3000 = qmi.make_instrument('dim3000', TimeBase_Dim3000, "foo")
        self.instr.open()

    def tearDown(self) -> None:
        if self.instr.is_open():
            self.instr.close()
        qmi.stop()

    def test_init(self):
        expected_default_attrs = {'baudrate': 19200}
        self._transport_factory.assert_called_once_with(ANY,
                                                        default_attributes=expected_default_attrs)

    def test_open(self):
        self._transport_mock.open.assert_called_once()

    def test_close(self):
        self.instr.close()
        self._transport_mock.close.assert_called_once()

    def test_bad_string(self):
        self._transport_mock.read_until.return_value = b'error\n'
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_device_info()

    def test_get_device_info(self):
        self._transport_mock.read_until.return_value = b'Rdev:ADRV4|Rhv:4|Rfv:5|Rfb:168|Rsn:111111\n'
        dev_info = self.instr.get_device_info()
        self._transport_mock.write.assert_called_with(b'Gdev\n')
        self.assertDictEqual(
            dict(dev='ADRV4', hv='4', fv='5', fb='168', sn='111111'),
            asdict(dev_info)
        )

    def test_get_idn(self):
        expected_idn = QMI_InstrumentIdentification("TimeBase", "DIM3000[ADRV4]", "111111", "4.5.168")
        self._transport_mock.read_until.return_value = b'Rdev:ADRV4|Rhv:4|Rfv:5|Rfb:168|Rsn:111111\n'
        actual_idn = self.instr.get_idn()
        self.assertTupleEqual(expected_idn, actual_idn)

    def test_get_init_data(self):
        self._transport_mock.read_until.return_value = b'Ramoffsmin:-225|Ramoffsmax:25|Ramoffsnom:0|Rinit:1\n'
        init_data = self.instr.get_init_data()
        self._transport_mock.write.assert_called_with(b'Ginit\n')
        self.assertDictEqual(
            dict(amoffsmin=-225, amoffsmax=25, amoffsnom=0, init=True, adcoffs=None, btstat=None),
            asdict(init_data)
        )

    def test_get_init_data_btstat(self):
        self._transport_mock.read_until.return_value = b'Ramoffsmin:-225|Ramoffsmax:25|Ramoffsnom:0|Rbtstat:0|Rinit:1\n'
        init_data = self.instr.get_init_data()
        self._transport_mock.write.assert_called_with(b'Ginit\n')
        self.assertDictEqual(
            dict(amoffsmin=-225, amoffsmax=25, amoffsnom=0, btstat=False, adcoffs=None, init=True),
            asdict(init_data)
        )

    def test_get_init_data_adcoffs(self):
        self._transport_mock.read_until.return_value = b'Ramoffsmin:-225|Ramoffsmax:25|Ramoffsnom:0|Radcoffs:-24|Rinit:1\n'
        init_data = self.instr.get_init_data()
        self._transport_mock.write.assert_called_with(b'Ginit\n')
        self.assertDictEqual(
            dict(amoffsmin=-225, amoffsmax=25, amoffsnom=0, btstat=None, adcoffs=-24, init=True),
            asdict(init_data)
        )

    def test_get_parameters(self):
        self._transport_mock.read_until.return_value = (
            b'Rfreq:39195001|Rampl:236|Rout:1|Rpmon:0|Rpmfr:34|Rpmd:200|Rpmphc:0|Rswpm:0|Rswps:20000000|'
            b'Rswpp:71000222|Rswpf:700|Rswpt:45000|Rfmon:0|Rfmdev:11|Rplson:0|Rplsfr:66|Rplsdt:50|'
            b'Rffreq:32000000|Rfampl:156|Ramoffs:0|Rpcbtemp:6175|Rrefstat:0|Rreflev:-85|Rvcclev:2418\n'
        )
        init_data = self.instr.get_parameters()
        self._transport_mock.write.assert_called_with(b'Gpar\n')
        self.assertDictEqual(
            dict(freq=39195001, ampl=23.6, out=True, swpm=DIM3000SweepMode.OFF, swps=20000000,
                 swpp=71000222, swpf=700, swpt=45000, fmon=False, fmdev=DIM3000FMDeviation._6553600HZ, plson=False, plsfr=66, plsdt=50,
                 ffreq=32000000, fampl=15.6, amoffs=0, pcbtemp=61.75, refstat=False, reflev=-85, vcclev=24.18),
            asdict(init_data)
        )

    @patch.object(TimeBase_Dim3000, "MINIMUM_EXEC_DELAY_S", new_callable=PropertyMock(return_value=0.0))
    def test_setters(self, _):
        self.instr.set_output_frequency(1000)
        self._transport_mock.write.assert_called_with(b'Sfreq:1000\n')

        with self.assertRaises(ValueError):
            self.instr.set_output_frequency(TimeBase_Dim3000.FREQ_RANGE[0]-1)

        with self.assertRaises(ValueError):
            self.instr.set_output_frequency(TimeBase_Dim3000.FREQ_RANGE[1]+1)

        self.instr.set_output_amplitude(15.4)
        self._transport_mock.write.assert_called_with(b'Sampl:154\n')

        self.instr.set_sweep_mode(DIM3000SweepMode.OFF)
        self._transport_mock.write.assert_called_with(b'Sswpm:0\n')

        self.instr.set_sweep_start_frequency(1000)
        self._transport_mock.write.assert_called_with(b'Sswps:1000\n')

        with self.assertRaises(ValueError):
            self.instr.set_sweep_start_frequency(TimeBase_Dim3000.FREQ_RANGE[0]-1)

        with self.assertRaises(ValueError):
            self.instr.set_sweep_start_frequency(TimeBase_Dim3000.FREQ_RANGE[1]+1)

        self.instr.set_sweep_stop_frequency(100)
        self._transport_mock.write.assert_called_with(b'Sswpp:100\n')

        with self.assertRaises(ValueError):
            self.instr.set_sweep_stop_frequency(TimeBase_Dim3000.FREQ_RANGE[0]-1)

        with self.assertRaises(ValueError):
            self.instr.set_sweep_stop_frequency(TimeBase_Dim3000.FREQ_RANGE[1]+1)

        self.instr.set_sweep_step_frequency(100)
        self._transport_mock.write.assert_called_with(b'Sswpf:100\n')

        with self.assertRaises(ValueError):
            self.instr.set_sweep_step_frequency(TimeBase_Dim3000.FREQ_RANGE[0]-1)

        with self.assertRaises(ValueError):
            self.instr.set_sweep_step_frequency(TimeBase_Dim3000.FREQ_RANGE[1]+1)

        self.instr.set_sweep_step_time(500)
        self._transport_mock.write.assert_called_with(b'Sswpt:500\n')

        with self.assertRaises(ValueError):
            self.instr.set_sweep_step_time(TimeBase_Dim3000.TIME_RANGE[0]-1)

        with self.assertRaises(ValueError):
            self.instr.set_sweep_step_time(TimeBase_Dim3000.TIME_RANGE[1]+1)

        self.instr.enable_fm_input()
        self._transport_mock.write.assert_called_with(b'Sfmon:1\n')

        self.instr.disable_fm_input()
        self._transport_mock.write.assert_called_with(b'Sfmon:0\n')

        self.instr.set_fm_deviation(DIM3000FMDeviation._104857600HZ)
        self._transport_mock.write.assert_called_with(b'Sfmdev:15\n')

        self.instr.enable_pulse_mode()
        self._transport_mock.write.assert_called_with(b'Splson:1\n')

        self.instr.disable_pulse_mode()
        self._transport_mock.write.assert_called_with(b'Splson:0\n')

        self.instr.set_pulse_frequency(1000)
        self._transport_mock.write.assert_called_with(b'Splsfr:1000\n')

        with self.assertRaises(ValueError):
            self.instr.set_pulse_frequency(TimeBase_Dim3000.PULSE_FREQ_RANGE[0]-1)

        with self.assertRaises(ValueError):
            self.instr.set_pulse_frequency(TimeBase_Dim3000.PULSE_FREQ_RANGE[1]+1)

        self.instr.set_pulse_duty_cycle(50)
        self._transport_mock.write.assert_called_with(b'Splsdt:50\n')

        with self.assertRaises(ValueError):
            self.instr.set_pulse_duty_cycle(TimeBase_Dim3000.DUTY_CYCLE_RANGE[0]-1)

        with self.assertRaises(ValueError):
            self.instr.set_pulse_duty_cycle(TimeBase_Dim3000.DUTY_CYCLE_RANGE[1]+1)

        self.instr.set_fsk_frequency(100)
        self._transport_mock.write.assert_called_with(b'Sffreq:100\n')

        with self.assertRaises(ValueError):
            self.instr.set_fsk_frequency(TimeBase_Dim3000.FREQ_RANGE[0]-1)

        with self.assertRaises(ValueError):
            self.instr.set_fsk_frequency(TimeBase_Dim3000.FREQ_RANGE[1]+1)

        self.instr.set_fsk_amplitude(30.6)
        self._transport_mock.write.assert_called_with(b'Sfampl:306\n')

        self.instr.set_am_offset(0)
        self._transport_mock.write.assert_called_with(b'Samoffs:0\n')

        with self.assertRaises(ValueError):
            self.instr.set_am_offset(TimeBase_Dim3000.AM_OFFSET_RANGE[0]-1)

        with self.assertRaises(ValueError):
            self.instr.set_am_offset(TimeBase_Dim3000.AM_OFFSET_RANGE[1]+1)
