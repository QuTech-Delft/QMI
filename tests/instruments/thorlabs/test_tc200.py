import unittest, unittest.mock
from unittest.mock import call
from collections.abc import Sequence

from qmi.instruments.thorlabs import Thorlabs_Tc200
from qmi.instruments.thorlabs.tc200 import *
from qmi.instruments.thorlabs.tc200 import _Query, _Command

import qmi.core.exceptions
from qmi.core.context import QMI_Context


class TestThorlabsTc200(unittest.TestCase):

    def setUp(self) -> None:
        unittest.mock.patch("qmi.core.transport.QMI_SerialTransport._validate_device_name")
        qmi_context = unittest.mock.MagicMock(spec=QMI_Context)
        qmi_context.name = "mockytemp"
        self.ser_address = "COM298"
        self.baudrate = 115200
        transport_id = "serial:{}".format(self.ser_address)
        self.thorlabs = Thorlabs_Tc200(qmi_context, "heet", transport_id)

    def test_open_close(self):
        with unittest.mock.patch("serial.Serial") as ser:
            self.thorlabs.open()
            self.thorlabs.close()

            ser.assert_called_once_with(
                self.ser_address,
                baudrate=self.baudrate,  # The rest are defaults
                bytesize=8,
                parity='N',
                rtscts=False,
                stopbits=1.0,
                timeout=0.04
                )

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_receive_response(self, mock_read):
        """See that the _receive_response method receives one block of data"""
        mock_read.return_value = bytearray("query_cmd?\rblablabla\r> ".encode('ascii'))
        expected = "blablabla"
        with unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            msg = self.thorlabs._receive_response()
            self.thorlabs.close()

        self.assertEqual(msg, expected)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_receive_response_with_parts(self, mock_read):
        """See that _receive_response method receives multiple parts of data"""
        mock_read.return_value = bytearray("fake_query?\rpart1\rpart2\rpart3\r> ".encode('ascii'))
        expected = "part1\npart2\npart3"
        with unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            msg = self.thorlabs._receive_response()
            self.thorlabs.close()

        self.assertEqual(msg, expected)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_receive_response_raises_unicodeerror(self, mock_read):
        """"An error should be raised if the extra data present is not of expected length"""
        mock_read.return_value = bytearray("fake_query?\r".encode('ascii') + b"\x81 > ")
        with unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
                self.thorlabs._receive_response()

            self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_query_response_raises_qmi_instrumentexception(self, mock_read):
        """"An error should be raised if the extra data present is not of expected length"""
        mock_read.return_value = bytearray(f"query_cmd?\rCMD_NOT_DEFINED\r> ".encode('ascii'))
        query_mock = unittest.mock.Mock(spec=_Query)
        query_mock.value = "Nonsense"
        with unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
                self.thorlabs._send_query(query_mock)

            self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_get_idn(self, mock_read):
        # arrange
        expected_call = _Query.IDENT.value + "\r"
        vendor = "Thorlabs"
        model_number = "567890"
        # no serial number
        smth_else = "not_needed"
        fw_version = "12.3.4"
        input_string = expected_call + " ".join([vendor, model_number, smth_else, fw_version]) + "\r> "
        expected = 'QMI_InstrumentIdentification(vendor=\'{}\', model=\'{}\', serial=\'{}\', version=\'{}\')'.format(
            vendor, model_number, "", fw_version)
        mock_read.return_value = bytearray(input_string.encode())
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            idn = self.thorlabs.get_idn()
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

        # assert
        self.assertEqual(str(idn), expected)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_get_status(self, mock_read):
        """Test that get_status() returns a set of "random" status bits."""
        # arrange
        expected_call = _Query.STATUS.value + "\r"
        expected_response = Tc200Status(
            output_state=OutputState(1),
            mode=Mode(0),
            sensor_type=SensorType(8),
            unit=DisplayUnit(0),
            alarm=SensorAlarmState(64),
            cycle_state=CycleState(0)
        )
        mock_read.return_value = bytearray(str(expected_call + "149 > ").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            status = self.thorlabs.get_status()
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

        # assert
        self.assertEqual(status, expected_response)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_get_status_raises_valueerror(self, mock_read):
        """Test that get_status() raises ValueError on invalid response."""
        # arrange
        status_call = _Query.STATUS.value + "\r"
        mock_read.return_value = bytearray("{}iob > ".format(status_call).encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException) as exc:
                self.thorlabs.get_status()
                pass

            self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_get_status_raises_unicodeerror(self, mock_read):
        """Test that get_status() raises ValueError on invalid response."""
        # arrange
        status_call = _Query.STATUS.value + "\r"
        mock_read.return_value = bytearray(status_call.encode() + b"\x81 > ")
        # act
        with unittest.mock.patch("serial.Serial"):
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
                self.thorlabs.get_status()

            self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_is_enabled(self, mock_read):
        """Test that get_enabled() returns expected state."""
        # arrange
        expected_call = _Query.STATUS.value + "\r"
        mock_read.return_value = bytearray(str(expected_call + "149 > ").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            status = self.thorlabs.is_enabled()
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

        # assert
        self.assertTrue(status)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_has_alarm(self, mock_read):
        """Test that has_alarm() returns expected state."""
        # arrange
        expected_call = _Query.STATUS.value + "\r"
        mock_read.return_value = bytearray(str(expected_call + "149 > ").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            status = self.thorlabs.has_alarm()
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

        # assert
        self.assertTrue(status)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_is_tuned(self, mock_read):
        """Test that is_tuned() returns expected state (True)."""
        # arrange
        expected_call = _Query.TUNED.value + "\r"
        mock_read.return_value = bytearray(str(expected_call + "1\r > ").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            status = self.thorlabs.is_tuned()
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

        # assert
        self.assertTrue(status)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_enable(self, mock_read):
        """Test that enable() enables the heater output."""
        # arrange
        expected_calls = [
            _Query.STATUS.value + "\r",
            _Query.STATUS.value + "\r",
            _Command.TOGGLE_ENABLE.value + "\r"
        ]
        mock_read.side_effect = [
            bytearray(str(expected_calls[0] + "1 > \r").encode("ascii")),
            bytearray(str(expected_calls[1] + "0 > \r").encode("ascii")),
            bytearray(str(expected_calls[2] + "OK > \r").encode("ascii"))
        ]
        expected_sequence: Sequence = map(call, map(str.encode, expected_calls))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.enable()
            self.thorlabs.close()
            wrt.assert_has_calls(expected_sequence, any_order=True)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_enable_not_needed(self, mock_read):
        """Test that enable() does not call TOGGLE_ENABLE if already enabled."""
        # arrange
        expected_calls = [
            _Query.STATUS.value + "\r",
            _Query.STATUS.value + "\r",
        ]
        mock_read.side_effect = [
            bytearray(str(expected_calls[0] + "1 > \r").encode("ascii")),
            bytearray(str(expected_calls[1] + "1 > \r").encode("ascii")),
        ]
        expected_sequence: Sequence = map(call, map(str.encode, expected_calls))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.enable()
            self.thorlabs.close()
            wrt.assert_has_calls(expected_sequence, any_order=True)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_enable_excepts(self, mock_read):
        """Test that enable() excepts if it has alarm."""
        # arrange
        expected_call = _Query.STATUS.value + "\r"
        mock_read.return_value = bytearray(str(expected_call + "149 > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
                self.thorlabs.enable()

            self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_disable(self, mock_read):
        """Test that disable() disables the heater output."""
        # arrange
        expected_calls = [
            _Query.STATUS.value + "\r",
            _Command.TOGGLE_ENABLE.value + "\r"
        ]
        mock_read.side_effect = [
            bytearray(str(expected_calls[0] + "1 > \r").encode("ascii")),
            bytearray(str(expected_calls[1] + "OK > \r").encode("ascii"))
        ]
        expected_sequence: Sequence = map(call, map(str.encode, expected_calls))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.disable()
            self.thorlabs.close()
            wrt.assert_has_calls(expected_sequence, any_order=True)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_disable_not_needed(self, mock_read):
        """Test that disable() does not call TOGGLE_ENABLE if already disabled."""
        # arrange
        expected_call = _Query.STATUS.value + "\r"
        mock_read.return_value = bytearray(str(expected_call + "0 > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.disable()
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_temperature(self, mock_read):
        """Test that set_temperature() command is sent."""
        # arrange
        temperature = 25.0
        expected_call = _Command.SET_TEMPERATURE.value + f"={temperature:.1f}\r"
        mock_read.return_value = bytearray(str(expected_call + "OK > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.set_temperature(temperature)
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_temperature_out_of_range(self, mock_read):
        """Test that set_temperature() raises exceptions when T is out of range."""
        # arrange
        temperatures = [TMIN - 1, TMAX + 1]
        set_calls = [_Command.SET_TEMPERATURE.value + f"={temperatures[0]:.1f}\r",
                     _Command.SET_TEMPERATURE.value + f"={temperatures[1]:.1f}\r"
        ]
        for t, set_call in enumerate(set_calls):
            mock_read.return_value = bytearray(str(set_call + "OK > \r").encode("ascii"))
            # act
            with unittest.mock.patch("serial.Serial"), \
                    unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write"):
                self.thorlabs.open()
                with self.assertRaises(qmi.core.exceptions.QMI_UsageException):
                    self.thorlabs.set_temperature(temperatures[t])

                self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_temperature_hardware_error(self, mock_read):
        """Test that set_temperature() command catches a hardware error."""
        # arrange
        temperature = 25.0
        mock_read.return_value = bytearray((_Command.SET_TEMPERATURE.value +
                                            "\rCMD_ARG_RANGE_ERR > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write"):
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
                self.thorlabs.set_temperature(temperature)

            self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_get_temperature_setpoint(self, mock_read):
        """Test that get_temperature_setpoint() obtains expected T setpoint."""
        # arrange
        temperature = 25.0
        expected_call = _Query.SETPOINT_TEMPERATURE.value + "\r"
        mock_read.return_value = bytearray((expected_call + f"{temperature:.1f} Celsius\r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            response = self.thorlabs.get_temperature_setpoint()
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

        self.assertEqual(response, temperature)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_get_temperature_actual(self, mock_read):
        """Test that get_temperature_setpoint() obtains expected T setpoint."""
        # arrange
        temperature = 25.0
        expected_call = _Query.ACTUAL_TEMPERATURE.value + "\r"
        mock_read.return_value = bytearray((expected_call + f"{temperature:.1f} C\r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            response = self.thorlabs.get_temperature_actual()
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

        self.assertEqual(response, temperature)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_temperature_limit(self, mock_read):
        """Test that set_temperature_limit() command is sent."""
        # arrange
        temperature = 25.0
        expected_call = _Command.MAX_TEMPERATURE.value + f"={temperature:.1f}\r"
        mock_read.return_value = bytearray(str(expected_call + "OK > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.set_temperature_limit(temperature)
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_temperature_limit_out_of_range(self, mock_read):
        """Test that set_temperature_limit() raises exceptions when T is out of range."""
        # arrange
        temperatures = [TLIMIT_MIN - 1, TLIMIT_MAX + 1]
        set_calls = [_Command.MAX_TEMPERATURE.value + f"={temperatures[0]:.1f}\r",
                     _Command.MAX_TEMPERATURE.value + f"={temperatures[1]:.1f}\r"
        ]
        for t, set_call in enumerate(set_calls):
            mock_read.return_value = bytearray(str(set_call + "OK > \r").encode("ascii"))
            # act
            with unittest.mock.patch("serial.Serial"), \
                    unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write"):
                self.thorlabs.open()
                with self.assertRaises(qmi.core.exceptions.QMI_UsageException):
                    self.thorlabs.set_temperature_limit(temperatures[t])

                self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_temperature_limit_hardware_error(self, mock_read):
        """Test that set_temperature_limit() command catches a hardware error."""
        # arrange
        temperature = 25.0
        mock_read.return_value = bytearray((_Command.MAX_TEMPERATURE.value +
                                            "\rCMD_ARG_RANGE_ERR > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write"):
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
                self.thorlabs.set_temperature_limit(temperature)

            self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_get_temperature_limit(self, mock_read):
        """Test that get_temperature_limit() obtains expected T limit."""
        # arrange
        temperature = 25.0
        expected_call = _Query.MAX_TEMPERATURE.value + "\r"
        mock_read.return_value = bytearray((expected_call + f"{temperature:.1f}\r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            response = self.thorlabs.get_temperature_limit()
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

        self.assertEqual(response, temperature)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_power_limit(self, mock_read):
        """Test that set_power_limit() command is sent."""
        # arrange
        power = 10.0
        expected_call = _Command.MAX_POWER.value + f"={power:.1f}\r"
        mock_read.return_value = bytearray(str(expected_call + "OK > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.set_power_limit(power)
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_power_limit_out_of_range(self, mock_read):
        """Test that set_power_limit() raises exceptions when P is out of range."""
        # arrange
        powers = [PLIMIT_MIN - 1, PLIMIT_MAX + 1]
        set_calls = [_Command.MAX_POWER.value + f"={powers[0]:.1f}\r",
                     _Command.MAX_POWER.value + f"={powers[1]:.1f}\r"
        ]
        for t, set_call in enumerate(set_calls):
            mock_read.return_value = bytearray(str(set_call + "OK > \r").encode("ascii"))
            # act
            with unittest.mock.patch("serial.Serial"), \
                    unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write"):
                self.thorlabs.open()
                with self.assertRaises(qmi.core.exceptions.QMI_UsageException):
                    self.thorlabs.set_power_limit(powers[t])

                self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_power_limit_hardware_error(self, mock_read):
        """Test that set_power_limit() command catches a hardware error."""
        # arrange
        power = 10.0
        mock_read.return_value = bytearray((_Command.MAX_POWER.value +
                                            "\rCMD_ARG_RANGE_ERR > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write"):
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
                self.thorlabs.set_power_limit(power)

            self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_get_power_limit(self, mock_read):
        """Test that get_power_limit() obtains expected P limit."""
        # arrange
        power = 12.0
        expected_call = _Query.MAX_POWER.value + "\r"
        mock_read.return_value = bytearray((expected_call + f"{power:.1f}\r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            response = self.thorlabs.get_power_limit()
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

        self.assertEqual(response, power)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_pid_gains_p(self, mock_read):
        """Test that set_pid_gains(...) command is sent and sets proportional gain."""
        # arrange
        proportion = 10
        expected_call = _Command.PGAIN.value + f"={proportion}\r"
        mock_read.return_value = bytearray(str(expected_call + "OK > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.set_pid_gains(proportion, None, None)
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_pid_gains_i(self, mock_read):
        """Test that set_pid_gains(...) command is sent and sets integralal gain."""
        # arrange
        integral = 10
        expected_call = _Command.IGAIN.value + f"={integral}\r"
        mock_read.return_value = bytearray(str(expected_call + "OK > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.set_pid_gains(None, integral, None)
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_pid_gains_d(self, mock_read):
        """Test that set_pid_gains(...) command is sent and sets differentional gain."""
        # arrange
        differention = 10
        expected_call = _Command.DGAIN.value + f"={differention}\r"
        mock_read.return_value = bytearray(str(expected_call + "OK > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.set_pid_gains(None, None, differention)
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_pid_gains_all(self, mock_read):
        """Test that set_pid_gains(...) command is sent and sets all gains."""
        # arrange
        proportion = 10
        integral = 10
        differention = 10
        expected_calls = [_Command.PGAIN.value + f"={proportion}\r",
                          _Command.IGAIN.value + f"={integral}\r",
                          _Command.DGAIN.value + f"={differention}\r"
        ]
        mock_read.side_effect = [
            bytearray(str(expected_calls[0] + "OK > \r").encode("ascii")),
            bytearray(str(expected_calls[1] + "OK > \r").encode("ascii")),
            bytearray(str(expected_calls[2] + "OK > \r").encode("ascii"))
        ]
        expected_sequence: Sequence = map(call, map(str.encode, expected_calls))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.set_pid_gains(proportion, integral, differention)
            self.thorlabs.close()
            wrt.assert_has_calls(expected_sequence)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_pid_gains_out_of_range_for_p(self, mock_read):
        """Test that set_pid_gains(p, ...) raises exceptions when P is out of range."""
        # arrange
        proportionals = [PGAIN_MIN - 1, PGAIN_MAX + 1]
        set_calls = [_Command.PGAIN.value + f"={proportionals[0]}\r",
                     _Command.PGAIN.value + f"={proportionals[1]}\r"
        ]
        for t, set_call in enumerate(set_calls):
            mock_read.return_value = bytearray(str(set_call + "OK > \r").encode("ascii"))
            # act
            with unittest.mock.patch("serial.Serial"), \
                    unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write"):
                self.thorlabs.open()
                with self.assertRaises(qmi.core.exceptions.QMI_UsageException):
                    self.thorlabs.set_pid_gains(proportionals[t], None, None)

                self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_pid_gains_for_p_hardware_error(self, mock_read):
        """Test that set_pid_gains(p, ...) command catches a hardware error."""
        # arrange
        proportional = 10
        mock_read.return_value = bytearray((_Command.PGAIN.value +
                                            "\rCMD_ARG_RANGE_ERR > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write"):
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
                self.thorlabs.set_pid_gains(proportional, None, None)

            self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_pid_gains_out_of_range_for_i(self, mock_read):
        """Test that set_pid_gains(..., i, ...) raises exceptions when I is out of range."""
        # arrange
        integrals = [IGAIN_MIN - 1, IGAIN_MAX + 1]
        set_calls = [_Command.IGAIN.value + f"={integrals[0]}\r",
                     _Command.IGAIN.value + f"={integrals[1]}\r"
        ]
        for t, set_call in enumerate(set_calls):
            mock_read.return_value = bytearray(str(set_call + "OK > \r").encode("ascii"))
            # act
            with unittest.mock.patch("serial.Serial"), \
                    unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write"):
                self.thorlabs.open()
                with self.assertRaises(qmi.core.exceptions.QMI_UsageException):
                    self.thorlabs.set_pid_gains(None, integrals[t], None)

                self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_pid_gains_for_i_hardware_error(self, mock_read):
        """Test that set_pid_gains(..., i, ...) command catches a hardware error."""
        # arrange
        integral = 10
        mock_read.return_value = bytearray((_Command.IGAIN.value +
                                            "\rCMD_ARG_RANGE_ERR > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write"):
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
                self.thorlabs.set_pid_gains(None, integral, None)

            self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_pid_gains_out_of_range_for_d(self, mock_read):
        """Test that set_pid_gains(..., d) raises exceptions when D is out of range."""
        # arrange
        differentionals = [DGAIN_MIN - 1, DGAIN_MAX + 1]
        set_calls = [_Command.DGAIN.value + f"={differentionals[0]}\r",
                     _Command.DGAIN.value + f"={differentionals[1]}\r"
        ]
        for t, set_call in enumerate(set_calls):
            mock_read.return_value = bytearray(str(set_call + "OK > \r").encode("ascii"))
            # act
            with unittest.mock.patch("serial.Serial"), \
                    unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write"):
                self.thorlabs.open()
                with self.assertRaises(qmi.core.exceptions.QMI_UsageException):
                    self.thorlabs.set_pid_gains(None, None, differentionals[t])

                self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_set_pid_gains_for_d_hardware_error(self, mock_read):
        """Test that set_pid_gains(d, ...) command catches a hardware error."""
        # arrange
        differentional = 10
        mock_read.return_value = bytearray((_Command.DGAIN.value +
                                            "\rCMD_ARG_RANGE_ERR > \r").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write"):
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_InstrumentException):
                self.thorlabs.set_pid_gains(None, None, differentional)

            self.thorlabs.close()

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_get_pid_gains(self, mock_read):
        """Test that get_pid_gains() obtains expected P, I, D values."""
        # arrange
        proportional, integral, differential = 12, 11, 13
        expected_call = _Query.PID_GAINS.value + "\r"
        mock_read.return_value = bytearray(
            (expected_call + f"{proportional} {integral} {differential}\r").encode("ascii")
        )
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            p_gain, i_gain, d_gain = self.thorlabs.get_pid_gains()
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())

        self.assertEqual(p_gain, proportional)
        self.assertEqual(i_gain, integral)
        self.assertEqual(d_gain, differential)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_tune(self, mock_read):
        """Test that tune() tunes the temperature offset."""
        # arrange
        expected_calls = [
            _Query.STATUS.value + "\r",
            _Query.TUNED.value + "\r",
            _Command.TUNE_OFFSET.value + "\r"
        ]
        mock_read.side_effect = [
            bytearray(str(expected_calls[0] + "1 > \r").encode("ascii")),
            bytearray(str(expected_calls[1] + "0 \r> ").encode("ascii")),
            bytearray(str(expected_calls[2] + "OK > \r").encode("ascii"))
        ]
        expected_sequence: Sequence = map(call, map(str.encode, expected_calls))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.tune()
            self.thorlabs.close()
            wrt.assert_has_calls(expected_sequence, any_order=True)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_tune_excepts_alread_tuned(self, mock_read):
        """Test that tune() does excepts if already tuned."""
        # arrange
        expected_calls = [
            _Query.STATUS.value + "\r",
            _Query.TUNED.value + "\r",
        ]
        mock_read.side_effect = [
            bytearray(str(expected_calls[0] + "1 > \r").encode("ascii")),
            bytearray(str(expected_calls[1] + "1 \r> ").encode("ascii")),
        ]
        expected_error = "Device is already tuned"
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_UsageException) as exc:
                self.thorlabs.tune()

            self.thorlabs.close()
            self.assertEqual(str(exc.exception), expected_error)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_tune_excepts_if_heater_not_enabled(self, mock_read):
        """Test that tune() excepts if heater is not enabled."""
        # arrange
        expected_call = _Query.STATUS.value + "\r"
        mock_read.return_value = bytearray(str(expected_call + "0 \r> ").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            with self.assertRaises(qmi.core.exceptions.QMI_UsageException) as exc:
                self.thorlabs.tune()

            self.thorlabs.close()
            self.assertEqual(str(exc.exception), "Heater output must be enabled for tuning")

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_detune(self, mock_read):
        """Test that detune() detunes the temperature offset."""
        # arrange
        expected_calls = [
            _Query.TUNED.value + "\r",
            _Command.TUNE_OFFSET.value + "\r"
        ]
        mock_read.side_effect = [
            bytearray(str(expected_calls[0] + "1\r> ").encode("ascii")),
            bytearray(str(expected_calls[1] + "OK\r> ").encode("ascii"))
        ]
        expected_sequence: Sequence = map(call, map(str.encode, expected_calls))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.detune()
            self.thorlabs.close()
            wrt.assert_has_calls(expected_sequence, any_order=True)

    @unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.read_until")
    def test_detune_not_needed(self, mock_read):
        """Test that detune() does not call TUNE_OFFSET if already detuned."""
        # arrange
        expected_call = _Query.TUNED.value + "\r"
        mock_read.return_value = bytearray(str(expected_call + "0 \r> ").encode("ascii"))
        # act
        with unittest.mock.patch("serial.Serial"), \
                unittest.mock.patch("qmi.core.transport.QMI_SerialTransport.write") as wrt:
            self.thorlabs.open()
            self.thorlabs.detune()
            self.thorlabs.close()
            wrt.assert_called_once_with(expected_call.encode())


if __name__ == '__main__':
    unittest.main()
