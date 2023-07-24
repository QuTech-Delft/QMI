import unittest, unittest.mock
from typing import cast

from qmi.instruments.thorlabs import Thorlabs_Tsp01
from qmi.core.transport_usbtmc_visa import QMI_VisaUsbTmcTransport
import qmi.core.exceptions
from qmi.utils.context_managers import open_close


class TestThorlabsTsp01(unittest.TestCase):
    def setUp(self):
        qmi.start("TestTsp01Context")
        self._transport_mock = unittest.mock.MagicMock(spec=QMI_VisaUsbTmcTransport)
        with unittest.mock.patch(
                'qmi.instruments.thorlabs.tsp01.create_transport',
                return_value=self._transport_mock):
            self.instr: Thorlabs_Tsp01 = qmi.make_instrument("instr", Thorlabs_Tsp01, "transport_descriptor")
            self.instr = cast(Thorlabs_Tsp01, self.instr)

    def tearDown(self):
        qmi.stop()

    def test_open_close(self):
        """Test opening and closing the instrument"""
        self.instr.open()
        self.instr.close()

        self._transport_mock.open.assert_called_once()
        self._transport_mock.close.assert_called_once()

    def test_reset(self):
        """Test the reset method."""
        expected = [b"*RST\n", b"*OPC?\n"]
        with open_close(self.instr):
            self.instr.reset()

        self._transport_mock.write.assert_called_with(expected[1])
        self._transport_mock.write.assert_any_call(expected[0])

    def test_get_idn(self):
        """Test the get_idn method."""
        expected = b"*IDN?\n"
        expected_idn = ["Thorlabs", "TSP01", "59595", "1.23"]
        return_value_str = ",".join(expected_idn) + "\n"
        self._transport_mock.read_until.return_value = return_value_str.encode()
        with open_close(self.instr):
            idn = self.instr.get_idn()

        self._transport_mock.write.assert_called_with(expected)
        self.assertEqual(idn.vendor, expected_idn[0])
        self.assertEqual(idn.model, expected_idn[1])
        self.assertEqual(idn.serial, expected_idn[2])
        self.assertEqual(idn.version, expected_idn[3])

    def test_get_idn_excepts(self):
        """Test the get_idn method excepts if too many words are returned."""
        unexpected_idn = ["koekkoek", "Thorlabs", "TSP01", "59595", "1.23"]
        return_value_str = ",".join(unexpected_idn) + "\n"
        self._transport_mock.read_until.return_value = return_value_str.encode()
        with open_close(self.instr):
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
                self.instr.get_idn()

    def test_get_errors(self):
        """Test the get_errors method. Test both no errors and errors present cases."""
        expected = b"SYST:ERR?\n"
        expected_errors_1 = []
        expected_errors_2 = ["1,Very Serious Error", "2:Even Worse Error"]

        return_value_1 = b"0,What No Errors?\n"
        return_value_2 = expected_errors_2[0].encode() + b"\n"
        return_value_3 = expected_errors_2[1].encode() + b"\n"

        # First test. The reading stops at first entry as it starts with "0," and returns empty list
        self._transport_mock.read_until.side_effect = [return_value_1]
        with open_close(self.instr):
            no_errs = self.instr.get_errors()

        self.assertListEqual(no_errs, expected_errors_1)
        self._transport_mock.write.assert_called_with(expected)

        # Second test. Reading stops at third entry only and returns a list of two errors
        self._transport_mock.read_until.side_effect = [return_value_2, return_value_3, return_value_1]
        with open_close(self.instr):
            errs = self.instr.get_errors()

        self.assertListEqual(errs, expected_errors_2)
        self._transport_mock.write.assert_called_with(expected)

    def test_get_temperature(self):
        """Test get_temperature method returns temperature value."""
        sensors = [1, 2, 3]
        expected = [f"MEAS:TEMP{i}?\n" for i in sensors]
        expected_values = [10.0, 100.0, -100.0]
        for s in range(3):
            return_value_str = str(expected_values[s]) + "\n"
            self._transport_mock.read_until.return_value = return_value_str.encode()
            with open_close(self.instr):
                t = self.instr.get_temperature(sensors[s])

            self.assertEqual(t, expected_values[s])
            self._transport_mock.write.assert_called_with(expected[s].encode())

    def test_get_temperature_excepts(self):
        """Test that get_temperature call excepts on wrong sensor number and invalid response"""
        sensors = [0, 1]
        cmd = "MEAS:TEMP1?"
        expected_errors = ["Unknown temperature sensor 0", "Unexpected response to {!r}, got {!r}".format(cmd, chr(1))]
        for s in range(2):
            return_value_str = chr(s) + "\n"
            self._transport_mock.read_until.return_value = return_value_str.encode()
            with open_close(self.instr), self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as err:
                self.instr.get_temperature(sensors[s])

            self.assertEqual(str(err.exception), expected_errors[s])

    def test_get_humidity(self):
        """Test that get_humidity call returns a value."""
        expected = b"MEAS:HUM?\n"
        return_value = 100.0
        return_value_str = str(return_value) + "\n"
        self._transport_mock.read_until.return_value = return_value_str.encode()
        with open_close(self.instr):
            h2o = self.instr.get_humidity()

        self.assertEqual(h2o, return_value)
        self._transport_mock.write.assert_called_with(expected)

    def test_get_humidity_excepts(self):
        """Test that get_humidity call excepts on unexpected response"""
        cmd = "MEAS:HUM?"
        err = "sata"
        expected_error = "Unexpected response to {!r}, got {!r}".format(cmd, err)
        return_value_str = err + "\n"
        self._transport_mock.read_until.return_value = return_value_str.encode()
        with open_close(self.instr), self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as err:
            self.instr.get_humidity()

        self.assertEqual(str(err.exception), expected_error)


if __name__ == '__main__':
    unittest.main()
