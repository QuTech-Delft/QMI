import unittest
from unittest.mock import Mock, patch, call

import qmi.core.exceptions
from qmi.core.exceptions import QMI_TimeoutException, QMI_InstrumentException
from qmi.instruments.nenion import Nenion_ValveController
from qmi.instruments.nenion.valve_controller import Status
from tests.patcher import PatcherQmiContext as QMI_Context


class InitializeTestCase(unittest.TestCase):
    def test_non_valid_transport_init(self):
        """Test that a non-valid transport string excepts."""
        transport = "usbtmc:invalid:stuff"
        with self.assertRaises(qmi.core.exceptions.QMI_TransportDescriptorException):
            Nenion_ValveController(QMI_Context("test1"), "Nenion_test1", transport)

    def test_tcp_transport(self):
        """Test that TCP transport gets created."""
        transport = "tcp:123.45.67.8:1214"
        controller = Nenion_ValveController(QMI_Context("test2"), "Nenion_TCP", transport)

        self.assertIsInstance(controller, Nenion_ValveController)
        self.assertEqual(transport, controller._transport_str)

    def test_serial_transport(self):
        """Test that serial transport gets created."""
        transport = "serial:COM0:baudrate=19200"
        controller = Nenion_ValveController(QMI_Context("test3"), "Nenion_serial", transport)

        self.assertIsInstance(controller, Nenion_ValveController)
        self.assertEqual(transport, controller._transport_str)


class ClassMethodsTestCase(unittest.TestCase):
    def setUp(self):
        Nenion_ValveController.DEFAULT_RESPONSE_TIMEOUT = 0.01
        self.transport_patch = Mock()
        self.transport_patch.write = Mock()
        with patch("qmi.instruments.nenion.valve_controller.create_transport", return_value=self.transport_patch):
            self.transport = "tcp:123.45.67.8:1215"
            self.controller = Nenion_ValveController(QMI_Context("test2"), "Nenion_TCP", self.transport)

    def tearDown(self):
        self.transport_patch.reset_mock()
        self.controller = None

    def test_open_close(self):
        """Test the open-close methods."""
        self.controller.open()
        self.controller.close()

        self.transport_patch.assert_has_calls([call.open(), call.close()])

    def test_get_status(self):
        """Test getting a status with all accepted return values."""
        for status_response in Status.__members__.keys():
            expected_status = Status[status_response].value
            expected_position = 12345
            position_str = f"{status_response}{expected_position}"
            self.transport_patch.write = Mock()
            self.transport_patch.read = Mock(side_effect=[s.encode() for s in position_str] + [QMI_TimeoutException])
            with self.controller:
                status = self.controller.get_status()

            self.assertEqual(expected_status, status.value)
            self.assertEqual(expected_position, status.position)
            self.transport_patch.write.assert_called_with(b"S\r")
            self.assertEqual(len(position_str) + 1, self.transport_patch.read.call_count)

    def test_get_status_excepts(self):
        """See that get_status excepts if response is not a valid type."""
        status_response = "CP"
        expected_position = 12345
        position_str = f"{status_response}{expected_position}"
        self.transport_patch.read = Mock(side_effect=[s.encode() for s in position_str] + [QMI_TimeoutException])
        with self.controller:
            with self.assertRaises(QMI_InstrumentException):
                self.controller.get_status()

    def test_enable_motor_current(self):
        """Test setting enable_motor_current."""
        expected_call = b"E\r"
        with self.controller:
            self.controller.enable_motor_current()

        self.transport_patch.write.assert_called_with(expected_call)

    def test_disable_motor_current(self):
        """Test setting disable_motor_current."""
        expected_call = b"D\r"
        with self.controller:
            self.controller.disable_motor_current()

        self.transport_patch.write.assert_called_with(expected_call)

    def test_fully_close(self):
        """Test fully_close."""
        expected_call = b"N\r"
        with self.controller:
            self.controller.fully_close()

        self.transport_patch.write.assert_called_with(expected_call)

    # TODO: Need to mock position check after halting. def test_halt(self):
    #     """Test halt_motor."""
    #     expected_calls = [call.write(b"H\r"), call.write(b"S\r")]
    #     with self.controller:
    #         self.controller.halt_motor()
    #
    #     self.transport_patch.write.has_calls(expected_calls)


if __name__ == '__main__':
    unittest.main()
