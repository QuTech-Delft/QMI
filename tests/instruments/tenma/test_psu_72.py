""" Testcase of the Tenma series 72 power supply units."""
import unittest
from unittest.mock import call, patch

import qmi
from qmi.core.transport import QMI_UdpTransport
from qmi.core.exceptions import QMI_InstrumentException, QMI_UsageException
from qmi.instruments.tenma import Tenma72_2550


class TestTenma72_2550(unittest.TestCase):
    """ Testcase of the TestTenma72_2550 oscillopsu """

    def setUp(self):
        qmi.start("TestSiglentTenma72_2550")
        # Add patches
        patcher = patch('qmi.instruments.tenma.psu_72.create_transport', spec=QMI_UdpTransport)
        self._transport_mock = patcher.start().return_value
        self.addCleanup(patcher.stop)
        # Make DUT
        self.psu: Tenma72_2550 = qmi.make_instrument("Tenma72_2550", Tenma72_2550, "")
        self.psu.open()

    def tearDown(self):
        self.psu.close()
        qmi.stop()

    def test_get_idn(self):
        """ Test case for `get_idn(...)` function. """
        # arrange
        expected_vendor = "TENMA"
        expected_model = "72-2535"
        expected_serial = "1231345"
        expected_version = "2.0"
        self._transport_mock.read_until_timeout.return_value = "TENMA 72-2535 SN:1231345 V2.0".encode("ascii")
        expected_calls = [call.read_until_timeout(50, 0.2)]
        # act
        idn = self.psu.get_idn()
        # assert
        self.assertEqual(expected_calls, self._transport_mock.read_until_timeout.call_args_list)
        self.assertEqual(expected_vendor, idn.vendor)
        self.assertEqual(expected_model, idn.model)
        self.assertEqual(expected_serial, idn.serial)
        self.assertEqual(expected_version, idn.version)


if __name__ == '__main__':
    unittest.main()
