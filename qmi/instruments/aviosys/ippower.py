"""
Instrument driver for IP Power relay unit.
"""

from enum import Enum
from functools import partial
from ipaddress import IPv4Address
import logging
import re
import time
from typing import Dict, Optional
import urllib.error
import urllib.parse
import urllib.request

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException, QMI_TimeoutException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method


# Logger for this module
_logger = logging.getLogger(__name__)


# Default timeout for HTTP requests (seconds)
TIMEOUT = 5


class PowerSocket(Enum):
    """Socket identifiers."""
    P1 = "p61"
    P2 = "p62"
    P3 = "p63"
    P4 = "p64"


class Command(Enum):
    """Commands."""
    GETVERSION = "getversion"
    GETMAC = "getmac"
    GETPOWER = "getpower"
    SETPOWER = "setpower"
    CYCLEPOWER = "setpowercycle"


class PowerState(Enum):
    """Power state (on/off) for sockets."""
    OFF = 0
    ON = 1


def _parse_response(response):
    # Response is always in the form:
    #     <!--CGI-DATABEG-->\n<p>\n...</p>\n\n<!--CGI-DATAEND-->
    # We could use html.parser, but that seems overkill.
    payload = response.read()
    match = re.search(r"<p>(.*)</p>", payload.decode('utf-8'), re.DOTALL)

    if match is None:
        raise ValueError("Invalid response.")

    try:
        message = match.group(1).strip()
    except IndexError as exc:
        raise ValueError("Invalid response.") from exc

    return message


def _parse_status_string(status_string):
    # Status string is of the form p6x=X, ...
    try:
        state_strings = re.findall(r"(p6[0-9]{1}=[01]{1})", status_string)
        states = {PowerSocket(p): PowerState(int(s)) for p, s in map(partial(str.split, sep='='), state_strings)}
        # Also no match (empty dictionary 'states') should raise the exception
        if len(states) == 0:
            raise Exception

    except Exception as exc:
        raise QMI_InstrumentException("Instrument status string is invalid.") from exc

    return states


class IPPower9850(QMI_Instrument):
    """QMI driver for the IP Power relay unit."""

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 ipv4_address: str,
                 username: str = "admin",
                 password: str = "12345678") -> None:
        """Initialize the instrument driver.

        Parameters:
            context:        QMI Context.
            name:           Identifier for the instrument in the QMI context.
            ipv4_address:   IPv4 address of the device on the network.
            username:       Username (factory default: 'admin')
            password:       Associated password (factory default: '12345678')
        """
        super().__init__(context, name)

        self._host = IPv4Address(ipv4_address)  # raises ValueError for improper address
        self._baseurl = f"http://{self._host}"
        self._username = username
        self._password = password
        self._opener = None  # type: Optional[urllib.request.OpenerDirector]

    def _send_command(self, command, **kwargs):
        if self._opener is None:
            raise RuntimeError("Open device first")

        # Build the query url.
        params = {"cmd": command.value}
        for field, value in kwargs.items():
            params[field] = value
        url = "{}/set.cmd?{}".format(self._baseurl, urllib.parse.urlencode(params))
        _logger.debug("Request: %s", url)

        # Post request and check for response.
        req = urllib.request.Request(url, method="GET")
        try:
            with self._opener.open(req, timeout=TIMEOUT) as response:
                answer = _parse_response(response)
        except urllib.error.HTTPError as exc:
            raise QMI_InstrumentException("Error in communication with device") from exc

        return answer

    @rpc_method
    def open(self) -> None:
        """Open the device interface by issuing a HEAD request and check for a response."""
        _logger.info("Opening connection to IPPower9850 at %s", self._host)

        # Install a basic authentication handlers.
        auth_handler = urllib.request.HTTPBasicAuthHandler()
        auth_handler.add_password(realm="guest area",  # type: ignore  # defined in AbstractBasicAuthHandler.__init__()
                                  uri=self._baseurl,
                                  user=self._username,
                                  passwd=self._password)
        auth_handler.add_password(realm="user area",  # type: ignore  # defined in AbstractBasicAuthHandler.__init__()
                                  uri=self._baseurl,
                                  user=self._username,
                                  passwd=self._password)
        self._opener = urllib.request.build_opener(auth_handler)

        # Perform request and check for 200 OK response
        req = urllib.request.Request(self._baseurl, method="HEAD")
        try:
            resp = self._opener.open(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as exc:
            raise QMI_InstrumentException("Access denied for device at {}".format(self._host)) from exc
        except urllib.error.URLError as exc:
            raise QMI_TimeoutException("Unable to find a device at {}".format(self._host)) from exc

        if resp.status != 200:
            # This should not happen - exception should have been raised by urllib
            raise QMI_InstrumentException("Unknown error in accessing device at {}".format(self._host))

        return super().open()

    @rpc_method
    def close(self) -> None:
        """Close the device interface."""
        # Nothing to be done.
        return super().close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """Retrieve the device identification.

        The MAC address of the device is used as unique serial number. The version field holds the firmware version.
        """
        # Fixed vendor and model, no way to query it
        vendor = "Aviosys"
        model = "IP Power 9850XX"  # XX denotes socket type; for Schuko it is GE

        # Use MAC address as serial number (response is of the form 'mac=...' with no formatting (just 12 letters))
        mac = self._send_command(Command.GETMAC).split('=')[1]
        mac_formatted = ':'.join(mac[i:i+2] for i in range(0, 12, 2))

        # Firmware version (response is of the form 'Version=...')
        version = self._send_command(Command.GETVERSION).split('=')[1]  # firmware version
        return QMI_InstrumentIdentification(vendor=vendor, model=model, serial=mac_formatted, version=version)

    @rpc_method
    def get_all_states(self) -> Dict[PowerSocket, PowerState]:
        """Retrieve the power state of all channels."""
        response_message = self._send_command(Command.GETPOWER)
        return _parse_status_string(response_message)

    @rpc_method
    def get_state(self, channel: PowerSocket) -> PowerState:
        """Retrieve the power state of a single specific channel.

        Parameters:
            channel:    power socket identifier.
        """
        all_states = self.get_all_states()
        return all_states[channel]

    @rpc_method
    def set_state(self, channel: PowerSocket, target_state: PowerState) -> bool:
        """Set the power state for a single specified channel.

        Parameters:
            channel:        power socket identifier.
            target_state:   target state (on/off).

        Returns:
            True if state was set successfully, False otherwise.
        """
        args = {channel.value: target_state.value}
        status_string = self._send_command(Command.SETPOWER, **args)
        new_state = _parse_status_string(status_string)
        return new_state[channel] == target_state

    @rpc_method
    def set_states(self, target_states: Dict[PowerSocket, PowerState]) -> bool:
        """Set the power state of multiple channels at once.

        Parameters:
            target_states:  mapping of channels to target states (on/off).

        Returns:
            True if all states were set successfully, False otherwise.
        """
        args = {channel.value: target_state.value for channel, target_state in target_states.items()}
        status_string = self._send_command(Command.SETPOWER, **args)
        new_states = _parse_status_string(status_string)
        return all(new_states[p] == target_states[p] for p in target_states.keys())

    @rpc_method
    def set_all_off(self) -> bool:
        """Turn off all channels.

        Returns:
            True if all states were set off successfully, False otherwise.
        """
        target_states = {channel: PowerState.OFF for channel in PowerSocket}
        return self.set_states(target_states)

    @rpc_method
    def set_all_on(self) -> bool:
        """Turn on all channels.

        Returns:
            True if all states were set on successfully, False otherwise.
        """
        target_states = {channel: PowerState.ON for channel in PowerSocket}
        return self.set_states(target_states)

    @rpc_method
    def cycle(self, channel: PowerSocket, wait: int = 1, *, block: bool = False) -> bool:
        """Cycle power.

        For the specified channel the power is turned off and then, after `wait` seconds, turned back on.

        Note: the device returns OK when the command is accepted, so an additional check is needed to see if the
        cycle is actually successful. If `block` is True the routine will block until it verifies that the power is
        back on. It will block for at most `wait` + `ippower.TIMEOUT` seconds.

        Parameters:
            channel:    power socket identifier.
            wait:       wait time in seconds.
            block:      block until power cycling is verified.

        Returns:
            True if all channels cycled ok, False otherwise.
        """
        args = {channel.value: int(wait)}
        status_string = self._send_command(Command.CYCLEPOWER, **args)

        # Return message string is of the form p6x cycle ok, ...
        try:
            state_strings = re.findall(r"(p6[0-9]{1} cycle ok)", status_string)
            cycle_accepted = [PowerSocket(s[0:3]) for s in state_strings]
        except Exception as exc:
            raise QMI_InstrumentException("Instrument status string is invalid.") from exc

        accepted = channel in cycle_accepted
        cycle_ok = False
        if accepted and block:
            time.sleep(wait)
            t_start = time.monotonic()
            while time.monotonic() - t_start < TIMEOUT:
                time.sleep(0.1)
                if self.get_state(channel) == PowerState.ON:
                    cycle_ok = True
                    break
        else:
            cycle_ok = accepted

        return cycle_ok
