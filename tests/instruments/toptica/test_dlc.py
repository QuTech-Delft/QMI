"""Unit tests for Toptica DLC instrument driver."""

import unittest
from unittest.mock import Mock, patch, ANY

from qmi.instruments.toptica import Toptica_DlcPro


class TestTopticaDlc(unittest.TestCase):
    """Unit tests for DLC."""

    def setUp(self):
        self.transport = Mock(name="transport")

        patcher = patch("qmi.instruments.toptica.dlc.create_transport")
        patched_create_transport = patcher.start()
        patched_create_transport.return_value = self.transport
        self.addCleanup(patcher.stop)

        transport_string = "some_transport"
        self.dlc = Toptica_DlcPro(Mock(name="context"), "dlc_under_test", transport_string)
        patched_create_transport.assert_called_with(transport_string)

    def test_open_close(self):
        """Test initialization, open, close."""
        self.dlc.open()
        self.dlc.close()

        self.transport.open.assert_called_once()
        self.transport.read_until.assert_called_once_with(
            message_terminator=b"DeCoF Command Line\r\n> ", timeout=ANY)
        self.transport.close.assert_called_once()

    def test_open_fail(self):
        """Test failed open."""
        self.transport.read_until.side_effect = ValueError

        with self.assertRaises(Exception):
            self.dlc.open()

        self.transport.open.assert_called_once()
        self.transport.close.assert_called_once()

    def test_get_parameter_float(self):
        """Test parameter getter."""
        parameter_name = "my_param"
        parameter_value = 123.456
        self.transport.read_until.side_effect = [
            f"{parameter_value}\n".encode(),
            b"> \n"  # prompt
        ]

        retval = self.dlc.get_parameter(parameter_name)
        self.transport.write.assert_any_call(f"(param-ref '{parameter_name})\n".encode())
        self.assertEqual(retval, parameter_value)

    def test_get_parameter_int(self):
        """Test parameter getter."""
        parameter_name = "my_param"
        parameter_value = 123
        self.transport.read_until.side_effect = [
            f"{parameter_value}\n".encode(),
            b"> \n"  # prompt
        ]

        retval = self.dlc.get_parameter(parameter_name)
        self.transport.write.assert_any_call(f"(param-ref '{parameter_name})\n".encode())
        self.assertEqual(retval, parameter_value)

    def test_get_parameter_string(self):
        """Test parameter getter."""
        parameter_name = "my_param"
        parameter_value = "my_value"
        self.transport.read_until.side_effect = [
            f"\"{parameter_value}\"\n".encode(),
            b"> \n"  # prompt
        ]

        retval = self.dlc.get_parameter(parameter_name)
        self.transport.write.assert_any_call(f"(param-ref '{parameter_name})\n".encode())
        self.assertEqual(retval, parameter_value)

    def test_get_parameter_bool_true(self):
        """Test parameter getter."""
        parameter_name = "my_param"
        parameter_value = True
        self.transport.read_until.side_effect = [
            f"#t\n".encode(),
            b"> \n"  # prompt
        ]

        retval = self.dlc.get_parameter(parameter_name)
        self.transport.write.assert_any_call(f"(param-ref '{parameter_name})\n".encode())
        self.assertEqual(retval, parameter_value)

    def test_get_parameter_bool_false(self):
        """Test parameter getter."""
        parameter_name = "my_param"
        parameter_value = False
        self.transport.read_until.side_effect = [
            f"#f\n".encode(),
            b"> \n"  # prompt
        ]

        retval = self.dlc.get_parameter(parameter_name)
        self.transport.write.assert_any_call(f"(param-ref '{parameter_name})\n".encode())
        self.assertEqual(retval, parameter_value)

    def test_get_parameter_tuple(self):
        """Test parameter getter."""
        parameter_name = "my_param"
        parameter_value = (12, 34.56, "hello")
        self.transport.read_until.side_effect = [
            f"{parameter_value}\n".replace('\'', '"').replace(',', ' ').encode(),  # strings must have double quotes!
            b"> \n"  # prompt
        ]

        retval = self.dlc.get_parameter(parameter_name)
        self.transport.write.assert_any_call(f"(param-ref '{parameter_name})\n".encode())
        self.assertEqual(retval, parameter_value)

    def test_get_multiple_parameter(self):
        """Test parameter getter."""
        parameter_names = ["my_param1", "my_param2", "my_param3"]
        parameter_values = (123, 456.789, "hello")
        self.transport.read_until.side_effect = [
            f"{parameter_values}\n".replace('\'', '"').replace(',', ' ').encode(),  # strings must have double quotes!
            b"> \n"  # prompt
        ]

        retval = self.dlc.get_multiple_parameters(parameter_names)
        self.transport.write.assert_any_call(
            "`(,(param-ref '{p[0]}),(param-ref '{p[1]}),(param-ref '{p[2]}))\n".format(p=parameter_names).encode()
        )
        self.assertEqual(retval, parameter_values)

    def test_get_parameter_error(self):
        """Test parameter getter."""
        self.transport.read_until.side_effect = [
            b"Error: this is an error\n",
            b"> \n"  # prompt
        ]
        with self.assertRaises(ValueError):
            self.dlc.get_parameter("my_param")

    def test_set_parameter_float(self):
        """Test parameter setter."""
        parameter_name = "my_param"
        parameter_value = 123.456
        self.transport.read_until.side_effect = [
            b"0\n",  # success
            b"> \n"  # prompt
        ]

        self.dlc.set_parameter(parameter_name, parameter_value)
        self.transport.write.assert_any_call(f"(param-set! '{parameter_name} {parameter_value})\n".encode())

    def test_set_parameter_int(self):
        """Test parameter setter."""
        parameter_name = "my_param"
        parameter_value = 123
        self.transport.read_until.side_effect = [
            b"0\n",  # success
            b"> \n"  # prompt
        ]

        self.dlc.set_parameter(parameter_name, parameter_value)
        self.transport.write.assert_any_call(f"(param-set! '{parameter_name} {parameter_value})\n".encode())

    def test_set_parameter_string(self):
        """Test parameter setter."""
        parameter_name = "my_param"
        parameter_value = "my_value"
        self.transport.read_until.side_effect = [
            b"0\n",  # success
            b"> \n"  # prompt
        ]

        self.dlc.set_parameter(parameter_name, parameter_value)
        self.transport.write.assert_any_call(f"(param-set! '{parameter_name} {parameter_value})\n".encode())

    def test_set_parameter_bool_true(self):
        """Test parameter setter."""
        parameter_name = "my_param"
        parameter_value = True
        self.transport.read_until.side_effect = [
            b"0\n",  # success
            b"> \n"  # prompt
        ]

        self.dlc.set_parameter(parameter_name, parameter_value)
        self.transport.write.assert_any_call(f"(param-set! '{parameter_name} #t)\n".encode())

    def test_set_parameter_bool_false(self):
        """Test parameter setter."""
        parameter_name = "my_param"
        parameter_value = False
        self.transport.read_until.side_effect = [
            b"0\n",  # success
            b"> \n"  # prompt
        ]

        self.dlc.set_parameter(parameter_name, parameter_value)
        self.transport.write.assert_any_call(f"(param-set! '{parameter_name} #f)\n".encode())

    def test_set_multiple_parameter(self):
        """Test parameter setter."""
        parameter_names = ["my_param1", "my_param2", "my_param3"]
        parameter_values = (123, 456.789, "hello")
        self.transport.read_until.side_effect = [
            b"0\n",
            b"> \n"  # prompt
        ]

        self.dlc.set_multiple_parameters(zip(parameter_names, parameter_values))
        self.transport.write.assert_any_call(
            "(+ (param-set! '{p[0]} {v[0]})(param-set! '{p[1]} {v[1]})(param-set! '{p[2]} {v[2]}))\n".format(
                p=parameter_names, v=parameter_values
            ).encode()
        )

    def test_set_parameter_error(self):
        """Test parameter setter."""
        self.transport.read_until.side_effect = [
            b"Error: this is an error\n",
            b"> \n"  # prompt
        ]
        with self.assertRaises(ValueError):
            self.dlc.set_parameter("my_param", 123.456)
