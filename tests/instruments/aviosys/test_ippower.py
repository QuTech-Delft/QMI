import unittest
from unittest.mock import patch, Mock, MagicMock
from ipaddress import IPv4Address
import urllib.error
import urllib.parse
import urllib.request

import qmi.instruments.aviosys.ippower
from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.instruments.aviosys import Aviosys_IpPower9850, PowerSocket, PowerState


class AviosysIPPower9850ClassTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._ipv4addess_patch = patch("qmi.instruments.aviosys.ippower.IPv4Address", autospec=IPv4Address)

    def test_instance_creation_with_defaults(self):
        """Test the creation of the IPPower9850 instance with default inputs."""
        # Arrange
        address = "123.123.123.0"
        self._ipv4addess_patch.return_value = address
        expected_baseurl = f"http://{address}"
        expected_username = "admin"
        expected_password = "12345678"
        # Act
        ippower = Aviosys_IpPower9850(QMI_Context("IPPower9850_test"), "ippower", address)
        # Assert
        self.assertEqual(ippower._baseurl, expected_baseurl)
        self.assertEqual(ippower._username, expected_username)
        self.assertEqual(ippower._password, expected_password)

    def test_instance_creation_with_custom_values(self):
        """Test the creation of the IPPower9850 instance with custom inputs."""
        # Arrange
        address = "111.222.210.12"
        self._ipv4addess_patch.return_value = address
        expected_baseurl = f"http://{address}"
        expected_username = "superuser"
        expected_password = "9876543210"
        # Act
        ippower = Aviosys_IpPower9850(
            QMI_Context("IPPower9850_test"), "ippower", address, username=expected_username, password=expected_password)
        # Assert
        self.assertEqual(ippower._baseurl, expected_baseurl)
        self.assertEqual(ippower._username, expected_username)
        self.assertEqual(ippower._password, expected_password)


class AviosysIPPower9850OpenCloseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._ipv4addess_patch = patch("qmi.instruments.aviosys.ippower.IPv4Address", autospec=IPv4Address)
        self._ipv4addess_patch.return_value = "10.10.10.1"
        self.ippower = Aviosys_IpPower9850(QMI_Context("IPPower9850_test"), "ippower", "10.10.10.1")

    @patch("qmi.instruments.aviosys.ippower.urllib.request", autospec=urllib.request)
    def test_open(self, request_patch):
        """Test the creation of the IPPower9850 instance with default inputs."""
        # Arrange
        expected_baseurl = "http://" + self._ipv4addess_patch.return_value
        request_patch.HTTPBasicAuthHandler = MagicMock()
        request_patch.Request = Mock()
        request_patch.build_opener().open().status = 200
        # Act
        self.ippower.open()
        # Assert
        request_patch.Request.assert_called_once_with(expected_baseurl, method="HEAD")

    @patch("qmi.instruments.aviosys.ippower.urllib.request", autospec=urllib.request)
    def test_open_access_denied(self, request_patch):
        """Test the open fails with "access denied" error."""
        # Arrange
        expected_error = "Access denied for device at {}".format(self._ipv4addess_patch.return_value)
        request_patch.HTTPBasicAuthHandler = MagicMock()
        request_patch.Request = Mock()
        class open_mock:
            def open(self, timeout):
                raise urllib.error.HTTPError("a", 1, "b", Mock(), Mock())

        request_patch.build_opener.return_value = open_mock
        # Act
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.ippower.open()

        # Assert
        self.assertEqual(expected_error, str(exc.exception))

    @patch("qmi.instruments.aviosys.ippower.urllib.request", autospec=urllib.request)
    def test_open_unable_to_find(self, request_patch):
        """Test the open fails with "unable to find" error."""
        # Arrange
        expected_error = "Unable to find a device at {}".format(self._ipv4addess_patch.return_value)
        request_patch.HTTPBasicAuthHandler = MagicMock()
        request_patch.Request = Mock()
        class open_mock:
            def open(self, timeout):
                raise urllib.error.URLError("a", "b")

        request_patch.build_opener.return_value = open_mock
        # Act
        with self.assertRaises(QMI_TimeoutException) as exc:
            self.ippower.open()

        # Assert
        self.assertEqual(expected_error, str(exc.exception))

    @patch("qmi.instruments.aviosys.ippower.urllib.request", autospec=urllib.request)
    def test_open_unknown_error(self, request_patch):
        """Test the open fails with unknown error."""
        # Arrange
        expected_error = "Unknown error in accessing device at {}".format(self._ipv4addess_patch.return_value)
        request_patch.HTTPBasicAuthHandler = MagicMock()
        request_patch.Request = Mock()
        # Act
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.ippower.open()

        # Assert
        self.assertEqual(expected_error, str(exc.exception))

    def test_close(self):
        """Test the close call."""
        # Arrange
        self.ippower._is_open = True  # Make instrument appear as "open"
        # Act
        self.ippower.close()
        # Assert
        self.assertFalse(self.ippower.is_open())

    def test_method_call_excepts_as_opener_is_none(self):
        """Test a method to except due to not having the self._opener yet defined."""
        # Act and Assert
        with self.assertRaises(RuntimeError):
            self.ippower.get_idn()


class AviosysIPPower9850MethodsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._ipv4addess_patch = patch("qmi.instruments.aviosys.ippower.IPv4Address", autospec=IPv4Address)
        self._ipv4addess_patch.return_value = "10.10.10.1"
        self.ippower = Aviosys_IpPower9850(QMI_Context("IPPower9850_test"), "ippower", "10.10.10.1")

        with patch("qmi.instruments.aviosys.ippower.urllib.request", autospec=urllib.request) as self.request_patch:
            self.request_patch.HTTPBasicAuthHandler = MagicMock()
            self.request_patch.Request = Mock()
            self.request_patch.build_opener().open().status = 200
            # open the instrument
            self.ippower.open()

    def tearDown(self) -> None:
        self.ippower.close()

    def test_parse_response_excepts(self):
        """Test with a method the _parse_response excepts with invalid response format."""
        # Arrange
        mac = "MAC=1A2B3C4D5E6F7G8H9I0J"
        expected_error = "Invalid response."
        mac_resp = f"{mac}".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(side_effect=[mac_resp])

        # Act
        with self.assertRaises(ValueError) as exc:
            self.ippower.get_idn()

        # Assert
        self.assertEqual(expected_error, str(exc.exception))

    def test_parse_status_string_excepts(self):
        """Test the _parse_status_string excepts at invalid response."""
        # Arrange
        expected_error = "Instrument status string is invalid."
        states = "p61=2p62=3p63=4p64=5"
        # Response is always in the form:
        #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
        state_resp = f"<!--CGI-DATABEG-->\n<p>\n{states}</p>\n\n<!--CGI-DATAEND-->".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(return_value=state_resp)

        # Act
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.ippower.get_all_states()

        # Assert
        self.assertEqual(expected_error, str(exc.exception))

    def test_send_command_excepts(self):
        """Test with a method the _send_command excepts with HTTPError."""
        # Arrange
        expected_error = "Error in communication with device"
        self.request_patch.build_opener().open().__enter__().read = Mock(
            side_effect=[urllib.error.HTTPError("a", 1, "b", Mock(), Mock())]
        )

        # Act
        with self.assertRaises(QMI_InstrumentException) as exc:
            self.ippower.get_idn()

        # Assert
        self.assertEqual(expected_error, str(exc.exception))

    def test_get_idn(self):
        """Test the get_idn method."""
        # Arrange
        mac = "MAC=1A2B3C4D5E6F7G8H9I0J"
        version = "Version=1.23.4"
        expected_vendor = "Aviosys"
        expected_model = "IP Power 9850XX"
        expected_serial = ":".join(mac[i:i+2] for i in range(4, 16, 2))
        expected_version = version.split("=")[1]
        # Response is always in the form:
        #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
        mac_resp = f"<!--CGI-DATABEG-->\n<p>\n{mac}</p>\n\n<!--CGI-DATAEND-->".encode()
        version_resp = f"<!--CGI-DATABEG-->\n<p>\n{version}</p>\n\n<!--CGI-DATAEND-->".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(side_effect=[mac_resp, version_resp])

        # Act
        idn = self.ippower.get_idn()

        # Assert
        self.assertEqual(expected_vendor, idn.vendor)
        self.assertEqual(expected_model, idn.model)
        self.assertEqual(expected_serial, idn.serial)
        self.assertEqual(expected_version, idn.version)

    def test_get_all_states(self):
        """Test the get_all_states method."""
        # Arrange
        expected_P61 = PowerState.OFF
        expected_P62 = PowerState.OFF
        expected_P63 = PowerState.ON
        expected_P64 = PowerState.OFF
        states = f"p61={expected_P61.value}p62={expected_P62.value}p63={expected_P63.value}p64={expected_P64.value}"
        # Response is always in the form:
        #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
        state_resp = f"<!--CGI-DATABEG-->\n<p>\n{states}</p>\n\n<!--CGI-DATAEND-->".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(return_value=state_resp)

        # Act
        resp = self.ippower.get_all_states()

        # Assert
        self.assertEqual(resp[PowerSocket.P1], expected_P61)
        self.assertEqual(resp[PowerSocket.P2], expected_P62)
        self.assertEqual(resp[PowerSocket.P3], expected_P63)
        self.assertEqual(resp[PowerSocket.P4], expected_P64)

    def test_get_state(self):
        """Test the get_state method."""
        # Arrange
        expected_P61 = PowerState.OFF
        expected_P62 = PowerState.OFF
        expected_P63 = PowerState.ON
        expected_P64 = PowerState.OFF
        states = f"p61={expected_P61.value}p62={expected_P62.value}p63={expected_P63.value}p64={expected_P64.value}"
        # Response is always in the form:
        #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
        state_resp = f"<!--CGI-DATABEG-->\n<p>\n{states}</p>\n\n<!--CGI-DATAEND-->".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(return_value=state_resp)

        # Act
        resp_P61 = self.ippower.get_state(PowerSocket.P1)
        resp_P62 = self.ippower.get_state(PowerSocket.P2)
        resp_P63 = self.ippower.get_state(PowerSocket.P3)
        resp_P64 = self.ippower.get_state(PowerSocket.P4)

        # Assert
        self.assertEqual(resp_P61, expected_P61)
        self.assertEqual(resp_P62, expected_P62)
        self.assertEqual(resp_P63, expected_P63)
        self.assertEqual(resp_P64, expected_P64)

    def test_set_state(self):
        """Test the set_state method."""
        # Arrange
        expected_P61 = PowerState.OFF
        expected_P62 = PowerState.OFF
        expected_P63 = PowerState.ON
        expected_P64 = PowerState.OFF
        states = f"p61={expected_P61.value}p62={expected_P62.value}p63={expected_P63.value}p64={expected_P64.value}"
        # Response is always in the form:
        #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
        state_resp = f"<!--CGI-DATABEG-->\n<p>\n{states}</p>\n\n<!--CGI-DATAEND-->".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(return_value=state_resp)

        # Act
        resp_P61 = self.ippower.set_state(PowerSocket.P1, expected_P61)
        resp_P62 = self.ippower.set_state(PowerSocket.P2, expected_P62)
        resp_P63 = self.ippower.set_state(PowerSocket.P3, expected_P63)
        resp_P64 = self.ippower.set_state(PowerSocket.P4, expected_P64)

        # Assert
        self.assertEqual(resp_P61, bool(expected_P61))
        self.assertEqual(resp_P62, bool(expected_P62))
        self.assertEqual(resp_P63, bool(expected_P63))
        self.assertEqual(resp_P64, bool(expected_P64))

    def test_set_states_true(self):
        """Test the set_states method."""
        # Arrange
        expected_P61 = PowerState.OFF
        expected_P62 = PowerState.OFF
        expected_P63 = PowerState.ON
        expected_P64 = PowerState.OFF
        set_states = {
            PowerSocket.P1: expected_P61,
            PowerSocket.P2: expected_P62,
            PowerSocket.P3: expected_P63,
            PowerSocket.P4: expected_P64,
        }
        states = f"p61={expected_P61.value}p62={expected_P62.value}p63={expected_P63.value}p64={expected_P64.value}"
        # Response is always in the form:
        #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
        state_resp = f"<!--CGI-DATABEG-->\n<p>\n{states}</p>\n\n<!--CGI-DATAEND-->".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(return_value=state_resp)

        # Act
        resp = self.ippower.set_states(set_states)

        # Assert
        self.assertTrue(resp)

    def test_set_states_false(self):
        """Test the set_states method."""
        # Arrange
        expected_P61 = PowerState.OFF
        expected_P62 = PowerState.OFF
        expected_P63 = PowerState.ON
        expected_P64 = PowerState.OFF
        set_states = {
            PowerSocket.P1: expected_P61,
            PowerSocket.P2: PowerState.ON,
            PowerSocket.P3: expected_P63,
            PowerSocket.P4: expected_P64,
        }
        states = f"p61={expected_P61.value}p62={expected_P62.value}p63={expected_P63.value}p64={expected_P64.value}"
        # Response is always in the form:
        #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
        state_resp = f"<!--CGI-DATABEG-->\n<p>\n{states}</p>\n\n<!--CGI-DATAEND-->".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(return_value=state_resp)

        # Act
        resp = self.ippower.set_states(set_states)

        # Assert
        self.assertFalse(resp)

    def test_set_all_off(self):
        """Test the set_all_off method."""
        # Arrange
        states = "p61=0p62=0p63=0p64=0"
        # Response is always in the form:
        #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
        state_resp = f"<!--CGI-DATABEG-->\n<p>\n{states}</p>\n\n<!--CGI-DATAEND-->".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(return_value=state_resp)

        # Act
        resp = self.ippower.set_all_off()

        # Assert
        self.assertTrue(resp)

    def test_set_all_on(self):
        """Test the set_all_on method."""
        # Arrange
        states = "p61=1p62=1p63=1p64=1"
        # Response is always in the form:
        #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
        state_resp = f"<!--CGI-DATABEG-->\n<p>\n{states}</p>\n\n<!--CGI-DATAEND-->".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(return_value=state_resp)

        # Act
        resp = self.ippower.set_all_on()

        # Assert
        self.assertTrue(resp)

    def test_cycle(self):
        """Test the cycle method."""
        # Arrange
        state_strings = "p61 cycle ok"
        # Response is always in the form:
        #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
        state_resp = f"<!--CGI-DATABEG-->\n<p>\n{state_strings}</p>\n\n<!--CGI-DATAEND-->".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(return_value=state_resp)

        # Act
        resp = self.ippower.cycle(PowerSocket.P1)

        # Assert
        self.assertTrue(resp)

    def test_cycle_with_block_and_wait(self):
        """Test the cycle method with block and wait input parameters."""
        # Arrange
        state_strings = "p61 cycle ok"
        # Response is always in the form:
        #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
        state_resp = f"<!--CGI-DATABEG-->\n<p>\n{state_strings}</p>\n\n<!--CGI-DATAEND-->".encode()
        states_0 = "<!--CGI-DATABEG-->\n<p>\np61=0p62=0p63=0p64=0</p>\n\n<!--CGI-DATAEND-->".encode()
        states_1 = "<!--CGI-DATABEG-->\n<p>\np61=1p62=0p63=0p64=0</p>\n\n<!--CGI-DATAEND-->".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(side_effect=[state_resp, states_0, states_1])

        # Act
        resp = self.ippower.cycle(PowerSocket.P1, wait=0.01, block=True)

        # Assert
        self.assertTrue(resp)

    def test_cycle_with_block_and_wait_cycle_nok(self):
        """Test the cycle method with block and wait input parameters, with nok cycle."""
        # Arrange
        qmi.instruments.aviosys.ippower.TIMEOUT = 1.0
        state_strings = "p61 cycle nok"
        # Response is always in the form:
        #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
        state_resp = f"<!--CGI-DATABEG-->\n<p>\n{state_strings}</p>\n\n<!--CGI-DATAEND-->".encode()
        states = "<!--CGI-DATABEG-->\n<p>\np61=0p62=0p63=0p64=0</p>\n\n<!--CGI-DATAEND-->".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(side_effect=[state_resp, states])

        # Act
        resp = self.ippower.cycle(PowerSocket.P1, wait=0.01, block=True)

        # Assert
        self.assertFalse(resp)

    def test_cycle_excepts(self):
        """Test the cycle method excepts on invalid status string."""
        # Arrange
        qmi.instruments.aviosys.ippower.TIMEOUT = 1.0
        state_strings = "p65 cycle ok"
        # Response is always in the form:
        #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
        state_resp = f"<!--CGI-DATABEG-->\n<p>\n{state_strings}</p>\n\n<!--CGI-DATAEND-->".encode()
        self.request_patch.build_opener().open().__enter__().read = Mock(return_value=state_resp)

        # Act and Assert
        with self.assertRaises(QMI_InstrumentException):
            self.ippower.cycle(PowerSocket.P1)


if __name__ == '__main__':
    unittest.main()
