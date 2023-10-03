import unittest
from unittest.mock import MagicMock, call, patch

from string import punctuation

from qmi.core.transport import QMI_TcpTransport
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.instruments.pi import PI_E873, ReferenceTarget


class TestE8738(unittest.TestCase):
    def setUp(self):
        self._transport_mock = MagicMock(spec=QMI_TcpTransport)
        with patch(
            "qmi.instruments.pi.e873.create_transport",
            MagicMock(return_value=self._transport_mock),
        ):
            self.instr = PI_E873(MagicMock(), "instr", "transport_descriptor")

    def tearDown(self):
        self.instr = None

    def _instr_open(self):
        """Open the instrument and clear the write mocked calls."""
        self._transport_mock.read_until.return_value = b"1\r\n"
        self.instr.open()
        self._transport_mock.write.reset_mock()

    def _test_parse_invalid(self, function, response):
        with self.assertRaises(QMI_InstrumentException):
            function(response, "", "")

    def _test_get_macros(self, function, command):
        self._instr_open()
        self._transport_mock.read_until.side_effect = [
            b"test1 \n",
            b"test2 \n",
            b"test3\n",
        ]
        m = function()
        self.instr.close()

        self._transport_mock.write.assert_called_once_with(
            f"{command}\n".encode("UTF-8")
        )
        self.assertEqual(m, ["test1", "test2", "test3"])

    def _test_variable_name_invalid(self, function, *args, **kwargs):
        def set_variable_helper(name):
            self._instr_open()
            with self.assertRaises(ValueError):
                function(name, *args, **kwargs)
            self.instr.close()

        set_variable_helper("A" * 9)  # char limit
        set_variable_helper("1")  # should start with a letter
        set_variable_helper(" BLA")  # should start with a letter
        set_variable_helper("BLA ")  # should end with a letter
        for i in punctuation:  # special characters
            set_variable_helper("BLA" + i)

    def _test_set_cmd_function(self, function, command):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"0\n"
        function(0.001)
        self.instr.close()

        self._transport_mock.write.assert_has_calls(
            [call(command.encode("UTF-8") + b" 1 0.00100000\n"), call(b"ERR?\n")]
        )

    def _test_float_get_address_function(self, function, address):
        self._instr_open()
        t = f"1 0X{address:X}".encode("UTF-8")
        self._transport_mock.read_until.return_value = t + b"=0.001\n"
        r = function()
        self.instr.close()

        self._transport_mock.write.assert_called_once_with(b"SPA? " + t + b"\n")
        self.assertEqual(r, 0.001)

    def _test_float_get_cmd_function(self, function, command):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"1=0.001\n"
        r = function()
        self.instr.close()

        self._transport_mock.write.assert_called_once_with(
            f"{command} 1\n".encode("UTF-8")
        )
        self.assertEqual(r, 0.001)

    def _test_bool_set_cmd_function(self, function, command):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"0\n"
        function(1)
        self.instr.close()

        self._transport_mock.write.assert_has_calls(
            [call(command.encode("UTF-8") + b" 1 1\n"), call(b"ERR?\n")]
        )

    def _test_bool_get_cmd_function(self, function, command):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"1=1\n"
        r = function()
        self.instr.close()

        self._transport_mock.write.assert_called_once_with(
            f"{command} 1\n".encode("UTF-8")
        )
        self.assertEqual(r, 1)

    def _test_dig_out_invalid(self, function, *args, **kwargs):
        self._instr_open()
        with self.assertRaises(QMI_InstrumentException):
            function(5, *args, **kwargs)
        self.instr.close()

    def _test_set_digital_output(self, function, command):
        for i in [1, 2, 3, 4]:
            self._instr_open()
            self._transport_mock.read_until.return_value = b"0\n"
            function(i, True)
            self._transport_mock.write.assert_has_calls(
                [
                    call(f"{command} {i} 1\n".encode("UTF-8")),
                    call(b"ERR?\n"),
                ]
            )
            self.instr.close()

    def _test_get_digital_output(self, function, command):
        for i in [1, 2, 3, 4]:
            self._instr_open()
            self._transport_mock.read_until.return_value = f"{i}=1\n".encode("UTF-8")
            s = function(i)
            self.instr.close()
            self._transport_mock.write.assert_called_once_with(
                f"{command} {i}\n".encode("UTF-8")
            )
            self.assertEqual(s, 1)

    def test_open_close(self):
        self._transport_mock.read_until.return_value = b"1\r\n"
        self.instr.open()
        self.instr.close()

        self._transport_mock.open.assert_called_once_with()
        self._transport_mock.write.assert_has_calls([call(b"ERR?\n"), call(b"SAI?\n")])
        self._transport_mock.close.assert_called_once_with()

    def test_open_invalid(self):
        self._transport_mock.read_until.return_value = b"2\r\n"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.open()
        self.instr.close()

    def test_ask_invalid(self):
        # Build a mock instrument to access ._ask
        instr = MagicMock(spec=PI_E873)
        instr._is_open = MagicMock(return_value=True)
        instr._transport = self._transport_mock

        def invalid_helper(value, exception):
            self._transport_mock.read_until.return_value = f"{value}".encode("UTF-8")
            with self.assertRaises(exception):
                PI_E873._ask(instr, "CMD")

        invalid_helper("", QMI_TimeoutException)
        invalid_helper(" ", QMI_InstrumentException)

    def test_parse_response_item_invalid(self):
        self._test_parse_invalid(PI_E873._parse_response_item, "\n\n")
        self._test_parse_invalid(PI_E873._parse_response_item, "NOKEY\n")

    def test_parse_int_invalid(self):
        self._test_parse_invalid(PI_E873._parse_int, "NOTINT")

    def test_parse_float_invalid(self):
        self._test_parse_invalid(PI_E873._parse_float, "NOTFLOAT")

    def test_reset(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"0\n"
        self.instr.reset()
        self.instr.close()

        self._transport_mock.write.assert_has_calls([call(b"RBT\n"), call(b"ERR?\n")])

    def test_get_idn(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = (
            b"vendor,model,serial,version\r\n"
        )
        i = self.instr.get_idn()
        self.instr.close()

        self._transport_mock.write.assert_called_once_with(b"*IDN?\n")
        self.assertEqual(i.vendor, "vendor")
        self.assertEqual(i.model, "model")
        self.assertEqual(i.serial, "serial")
        self.assertEqual(i.version, "version")

    def test_get_idn_invalid(self):
        self._instr_open()
        with self.assertRaises(QMI_InstrumentException):
            self._transport_mock.read_until.return_value = b"\n"
            self.instr.get_idn()
        self.instr.close()

        self._transport_mock.write.assert_called_once_with(b"*IDN?\n")

    def test_get_stage_info(self):
        self._instr_open()
        self._transport_mock.read_until.side_effect = r = []
        c = []
        for i in [1, 2, 3, 4]:
            t = f"1 0X{0X0F000000 + (i << 8):X}"
            r.append(f"{t}=result{i}\n".encode("UTF-8"))
            c.append(call(f"SPA? {t}\n".encode("UTF-8")))
        s = self.instr.get_stage_info()
        self.instr.close()

        self._transport_mock.write.assert_has_calls(c)
        self.assertEqual(s.type, "result1")
        self.assertEqual(s.serial_number, "result2")
        self.assertEqual(s.assembly_date, "result3")
        self.assertEqual(s.hw_version, "result4")

    def test_get_error(self):
        def get_error_helper(value):
            self._instr_open()
            self._transport_mock.read_until.return_value = f"{value}\n".encode("UTF-8")
            e = self.instr.get_error()
            self.instr.close()

            self._transport_mock.write.assert_called_once_with(b"ERR?\n")
            self.assertEqual(e, value)

        get_error_helper(0)
        get_error_helper(1)

    def test_get_system_status(self):
        sm = {
            # id: (shift, mask, val)
            "negative_limit_switch": (0, 0x1, 1),
            "reference_point_switch": (1, 0x1, 1),
            "positive_limit_switch": (2, 0x1, 1),
            "digital_input": (4, 0xF, (1, 1, 1, 1)),
            "error_flag": (8, 0x1, 1),
            "servo_mode": (12, 0x1, 1),
            "in_motion": (13, 0x1, 1),
            "on_target": (15, 0x1, 1),
        }

        for key, (s, m, v) in sm.items():
            self._instr_open()
            self._transport_mock.read_until.return_value = f"{m << s}\n".encode("UTF-8")
            ss = self.instr.get_system_status()
            self.instr.close()

            self._transport_mock.write.assert_called_once_with(b"\x04")
            self.assertEqual(
                i := getattr(ss, key), v, msg=f"{key}: is {i} expected {v}."
            )

    def test_stop_all(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"10\n"
        self.instr.stop_all()

        self._transport_mock.write.assert_any_call(b"\x18")
        self._transport_mock.write.assert_called_with(b"ERR?\n")

        self.instr.close()

    def test_stop_all_with_error(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"1\n"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.stop_all()
        self.instr.close()

    def test_stop_smooth(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"10\n"
        self.instr.stop_smooth()
        self.instr.close()

        self._transport_mock.write.assert_any_call(b"HLT\n")
        self._transport_mock.write.assert_called_with(b"ERR?\n")

    def test_get_physical_unit(self):
        self._instr_open()
        t = f"1 0X{0x07000601:X}".encode("UTF-8")
        self._transport_mock.read_until.return_value = t + b"=result\n"
        p = self.instr.get_physical_unit()
        self.instr.close()

        self._transport_mock.write.assert_called_once_with(b"SPA? " + t + b"\n")
        self.assertEqual(p, "result")

    def test_get_position_range(self):
        self._instr_open()
        self._transport_mock.read_until.side_effect = [
            b"1=0.001\r\n",
            b"1=0.002\r\n",
        ]
        p = self.instr.get_position_range()
        self.instr.close()

        self._transport_mock.write.assert_has_calls(
            [call(b"TMN? 1\n"), call(b"TMX? 1\n")]
        )
        self.assertEqual((0.001, 0.002), p)

    def test_get_max_position_error(self):
        self._test_float_get_address_function(self.instr.get_max_position_error, 0x8)

    def test_get_max_velocity(self):
        self._test_float_get_address_function(self.instr.get_max_velocity, 0xA)

    def test_get_max_acceleration(self):
        self._test_float_get_address_function(self.instr.get_max_acceleration, 0x4A)

    def test_get_max_deceleration(self):
        self._test_float_get_address_function(self.instr.get_max_deceleration, 0x4B)

    def test_get_reference_signal_mode(self):
        self._instr_open()
        t = f"1 0X{0x70:X}".encode("UTF-8")
        self._transport_mock.read_until.return_value = t + b"=1\n"
        m = self.instr.get_reference_signal_mode()
        self.instr.close()

        self._transport_mock.write.assert_called_once_with(b"SPA? " + t + b"\n")
        self.assertEqual(m.value, 1)

    def test_get_reference_velocity(self):
        self._test_float_get_address_function(self.instr.get_reference_velocity, 0x50)

    def test_set_acceleration(self):
        self._test_set_cmd_function(self.instr.set_acceleration, "ACC")

    def test_get_acceleration(self):
        self._test_float_get_cmd_function(self.instr.get_acceleration, "ACC?")

    def test_set_deceleration(self):
        self._test_set_cmd_function(self.instr.set_deceleration, "DEC")

    def test_get_deceleration(self):
        self._test_float_get_cmd_function(self.instr.get_deceleration, "DEC?")

    def test_set_velocity(self):
        self._test_set_cmd_function(self.instr.set_velocity, "VEL")

    def test_set_velocity_negative(self):
        self._instr_open()
        with self.assertRaises(QMI_InstrumentException):
            self.instr.set_velocity(-1)
        self.instr.close()

    def test_get_velocity(self):
        self._test_float_get_cmd_function(self.instr.get_velocity, "VEL?")

    def test_set_servo_mode(self):
        self._test_bool_set_cmd_function(self.instr.set_servo_mode, "SVO")

    def test_get_servo_mode(self):
        self._test_bool_get_cmd_function(self.instr.get_servo_mode, "SVO?")

    def test_set_reference_definition_mode(self):
        self._test_bool_set_cmd_function(
            self.instr.set_reference_definition_mode, "RON"
        )

    def test_get_reference_definition_mode(self):
        self._test_bool_get_cmd_function(
            self.instr.get_reference_definition_mode, "RON?"
        )

    def test_reference_move(self):
        def reference_move_helper(target, command):
            self._instr_open()
            self._transport_mock.read_until.return_value = b"0\n"
            self.instr.reference_move(target)
            self.instr.close()

            self._transport_mock.write.assert_has_calls(
                [call(command.encode("UTF-8") + b"\n"), call(b"ERR?\n")]
            )

        reference_move_helper(ReferenceTarget.REFERENCE_POINT, "FRF")
        reference_move_helper(ReferenceTarget.POSITIVE_LIMIT, "FPL")
        reference_move_helper(ReferenceTarget.NEGATIVE_LIMIT, "FNL")

    def test_get_reference_result(self):
        self._test_bool_get_cmd_function(self.instr.get_reference_result, "FRF?")

    def test_move_absolute(self):
        self._test_set_cmd_function(self.instr.move_absolute, "MOV")

    def test_move_relative(self):
        self._test_set_cmd_function(self.instr.move_relative, "MVR")

    def test_get_target_position(self):
        self._test_float_get_cmd_function(self.instr.get_target_position, "MOV?")

    def test_get_position(self):
        self._test_float_get_cmd_function(self.instr.get_position, "POS?")

    def test_wait_motion_complete(self):
        self._instr_open()
        self._transport_mock.read_until.side_effect = [
            f"{1<<13}\r\n".encode("UTF-8"),
            f"{1<<13}\r\n".encode("UTF-8"),
            f"{0<<13}\r\n".encode("UTF-8"),
        ]
        r = self.instr.wait_motion_complete()
        self.instr.close()
        self.assertEqual(r, True)

    def test_wait_motion_complete_timeout(self):
        self._instr_open()
        self._transport_mock.read_until.side_effect = [
            f"{1<<13}\r\n".encode("UTF-8"),
            f"{1<<13}\r\n".encode("UTF-8"),
            f"{1<<13}\r\n".encode("UTF-8"),
            f"{0<<13}\r\n".encode("UTF-8"),
        ]

        with patch("qmi.instruments.pi.e873.time.monotonic", side_effect=[0, 0, 100]):
            r = self.instr.wait_motion_complete(100)
            self.instr.close()

        self.assertEqual(r, False)

    def test_set_trigger_inmotion(self):
        for i in [1, 2, 3, 4]:
            self._instr_open()
            self._transport_mock.read_until.return_value = b"0\n"
            self.instr.set_trigger_inmotion(i)
            self.instr.close()
            self._transport_mock.write.assert_has_calls(
                [
                    call(f"CTO {i} 2 1\n".encode("UTF-8")),
                    call(f"CTO {i} 3 6\n".encode("UTF-8")),
                    call(b"ERR?\n"),
                ]
            )

    def test_set_trigger_inmotion_invalid(self):
        self._test_dig_out_invalid(self.instr.set_trigger_inmotion)

    def test_set_trigger_position_offset(self):
        for i in [1, 2, 3, 4]:
            self._instr_open()
            self._transport_mock.read_until.return_value = b"0\n"
            self.instr.set_trigger_position_offset(i, 0.1, 0.2, 0.3)
            self.instr.close()
            self._transport_mock.write.assert_has_calls(
                [
                    call(f"CTO {i} 2 1\n".encode("UTF-8")),
                    call(f"CTO {i} 1 {0.1:.8f}\n".encode("UTF-8")),
                    call(f"CTO {i} 10 {0.2:.8f}\n".encode("UTF-8")),
                    call(f"CTO {i} 9 {0.3:.8f}\n".encode("UTF-8")),
                    call(f"CTO {i} 3 7\n".encode("UTF-8")),
                    call(b"ERR?\n"),
                ]
            )

    def test_set_trigger_position_offset_invalid(self):
        self._test_dig_out_invalid(
            self.instr.set_trigger_position_offset, 0.1, 0.2, 0.3
        )

    def test_set_trigger_output_state(self):
        self._test_set_digital_output(self.instr.set_trigger_output_state, "TRO")

    def test_set_trigger_output_state_invalid(self):
        self._test_dig_out_invalid(self.instr.set_trigger_output_state, True)

    def test_get_trigger_output_state(self):
        self._test_get_digital_output(self.instr.get_trigger_output_state, "TRO?")

    def test_get_trigger_output_state_invalid(self):
        self._test_dig_out_invalid(self.instr.get_trigger_output_state)

    def test_set_digital_output(self):
        self._test_set_digital_output(self.instr.set_digital_output, "DIO")

    def test_set_digital_output_invalid(self):
        self._test_dig_out_invalid(self.instr.set_digital_output, True)

    def test_get_digital_input(self):
        self._test_get_digital_output(self.instr.get_digital_input, "DIO?")

    def test_get_digital_input_invalid(self):
        self._test_dig_out_invalid(self.instr.get_digital_input)

    def test_define_macro(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"0\n"
        c = ["TESTCMD1", "TESTCMD2", "TESTCMD3"]
        self.instr.define_macro("test", c)
        self.instr.close()

        self._transport_mock.write.assert_has_calls(
            [
                call(b"MAC BEG test\n"),
                call(b"TESTCMD1\n"),
                call(b"TESTCMD2\n"),
                call(b"TESTCMD3\n"),
                call(b"MAC END\n"),
                call(b"ERR?\n"),
            ]
        )

    def test_delete_macro(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"0\n"
        self.instr.delete_macro("test")
        self.instr.close()

        self._transport_mock.write.assert_has_calls(
            [
                call(b"MAC DEL test\n"),
                call(b"ERR?\n"),
            ]
        )

    def test_get_defined_macros(self):
        self._test_get_macros(self.instr.get_defined_macros, "MAC?")

    def test_start_macro(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"0\n"
        self.instr.start_macro("test", "arg1", "arg2")
        self.instr.close()

        self._transport_mock.write.assert_has_calls(
            [
                call(b"MAC START test arg1 arg2\n"),
                call(b"ERR?\n"),
            ]
        )

    def test_start_macro_repeat(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"0\n"
        self.instr.start_macro("test", "arg1", "arg2", 3)
        self.instr.close()

        self._transport_mock.write.assert_has_calls(
            [
                call(b"MAC NSTART test 3 arg1 arg2\n"),
                call(b"ERR?\n"),
            ]
        )

    def test_start_macro_invalid(self):
        self._instr_open()
        with self.assertRaises(QMI_InstrumentException):
            self.instr.start_macro("test", None, "arg2", 3)
        with self.assertRaises(QMI_InstrumentException):
            self.instr.start_macro("test", "arg1", "arg2", 0)
        self.instr.close()

    def test_get_running_macros(self):
        self._test_get_macros(self.instr.get_running_macros, "RMC?")

    def test_set_variable(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"0\n"
        self.instr.set_variable("test", None)
        self.instr.close()

        self._transport_mock.write.assert_has_calls(
            [
                call(b"VAR test\n"),
                call(b"ERR?\n"),
            ]
        )

    def test_set_variable_value(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"0\n"
        self.instr.set_variable("test", "valuetest")
        self.instr.close()

        self._transport_mock.write.assert_has_calls(
            [
                call(b"VAR test valuetest\n"),
                call(b"ERR?\n"),
            ]
        )

    def test_set_variable_invalid(self):
        self._test_variable_name_invalid(self.instr.set_variable, "")

    def test_get_variable(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"test=test1\n"
        variable = self.instr.get_variable("test")
        self.instr.close()

        self._transport_mock.write.assert_called_once_with(b"VAR? test\n")
        self.assertEqual(variable, "test1")

    def test_get_variable_invalid(self):
        self._test_variable_name_invalid(self.instr.get_variable)

    def test_get_variables(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = (
            b"test1=val1\ntest2=val2\ntest3=val3\n"
        )

        v = self.instr.get_variables()
        self.instr.close()

        self._transport_mock.write.assert_called_once_with(b"VAR?\n")
        self.assertEqual(
            v,
            {
                "test1": "val1",
                "test2": "val2",
                "test3": "val3",
            },
        )

    def test_get_variables_invalid(self):
        self._instr_open()
        self._transport_mock.read_until.return_value = b"NOKEY\n"
        with self.assertRaises(QMI_InstrumentException):
            self.instr.get_variables()
        self.instr.close()


if __name__ == "__main__":
    unittest.main()
