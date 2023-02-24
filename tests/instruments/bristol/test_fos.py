import sys
import unittest
from unittest.mock import Mock, call, patch

import qmi
import qmi.instruments.bristol.fos
from qmi.instruments.bristol.fos import Bristol_FOS
from qmi.utils.context_managers import open_close


class TestFos(unittest.TestCase):
    """ Unit tests for Bristol FOS. """

    UNIQUE_ID = 'DEADBEAF'
    
    def setUp(self):

        # Substitute a mock object in place of the "uldaq" module.
        # This must be done BEFORE the FOS driver runs "import uldaq".
        with patch.dict("sys.modules", {"uldaq": Mock()}):
            # Trigger lazy import of the uldaq module.
            qmi.instruments.bristol.fos._import_modules()

        # Patch device descriptor
        self.dev_desc = Mock()
        self.dev_desc.unique_id = self.UNIQUE_ID
        patcher = patch('qmi.instruments.bristol.fos.uldaq.get_daq_device_inventory',
                        return_value=[self.dev_desc])
        _ = patcher.start()
        self.addCleanup(patcher.stop)

        # Patch device
        self.device_mock = Mock()
        patcher = patch('qmi.instruments.bristol.fos.uldaq.DaqDevice',
                        return_value=self.device_mock)
        self.device_init = patcher.start()
        self.addCleanup(patcher.stop)

        # Start QMI
        qmi.start("test_fos", init_logging=False)

    def tearDown(self):
        # Stop QMI
        qmi.stop()

    def test_open_close(self):
        """Test open & close of the FOS."""

        # Pull data types from the mocked uldaq module.
        DigitalPortType = qmi.instruments.bristol.fos.uldaq.DigitalPortType
        DigitalDirection = qmi.instruments.bristol.fos.uldaq.DigitalDirection

        # arrange
        expected_calls = [
            call.connect(),
            call.get_dio_device(),
            call.disconnect(),
            call.release()
        ]

        expected_port_config = (
            DigitalPortType.FIRSTPORTA, DigitalDirection.OUTPUT
        )

        # act
        fos: Bristol_FOS = qmi.make_instrument("fos", Bristol_FOS, self.UNIQUE_ID)
        fos.open()
        fos.close()

        # assert
        self.assertEqual((self.dev_desc,), self.device_init.call_args[0])
        self.assertEqual(expected_calls, self.device_mock.method_calls)
        self.assertTupleEqual(expected_port_config, self.device_mock.get_dio_device.return_value.d_config_port.call_args[0])

    def test_device_not_found(self):
        """Test exception if device not found."""
        # act
        fos: Bristol_FOS = qmi.make_instrument("fos", Bristol_FOS, "wrong")

        # assert
        with self.assertRaises(ValueError):
            fos.open()

    def test_select_channel(self):
        """Test selecting channel"""

        # Pull data types from the mocked uldaq module.
        DigitalPortType = qmi.instruments.bristol.fos.uldaq.DigitalPortType

        # arrange
        test_channel = 1
        expected_d_out = (
            DigitalPortType.FIRSTPORTA, test_channel-1
        )
        
        # act
        with open_close(qmi.make_instrument("fos", Bristol_FOS, self.UNIQUE_ID)) as fos:
            fos.select_channel(test_channel)
        
        # assert
        self.assertTupleEqual(expected_d_out, self.device_mock.get_dio_device.return_value.d_out.call_args[0])

    def test_bad_channel(self):
        """Test bad channel"""
        # act & assert
        with self.assertRaises(ValueError):
            with open_close(qmi.make_instrument("fos", Bristol_FOS, self.UNIQUE_ID)) as fos:
                fos.select_channel(0)
