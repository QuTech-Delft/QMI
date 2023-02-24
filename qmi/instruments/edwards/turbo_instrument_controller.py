"""
Instrument driver for the Edwards Turbo Instrument Controller.
"""
import logging
import re
from typing import Dict

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)


class Edwards_TurboInstrumentController(QMI_Instrument):
    """Instrument driver for the Edwards Turbo Instrument Controller."""

    # default response timeout in seconds
    DEFAULT_RESPONSE_TIMEOUT = 5.0

    # command and response strings
    GENERAL_CMD_FORMAT = "!C{obj_id} {msg}"
    GENERAL_RESP_FORMAT = "*C{obj_id} "
    SETUP_CMD_FORMAT = "!S{obj_id} {data}"
    SETUP_RESP_FORMAT = "*S{obj_id} "
    QUERY_SETUP_CMD_FORMAT = "?S{obj_id}"
    QUERY_SETUP_RESP_ERR_FORMAT = "*S{obj_id} "
    QUERY_SETUP_RESP_FORMAT = "=S{obj_id} "
    QUERY_VALUE_CMD_FORMAT = "?V{obj_id}"
    QUERY_VALUE_RESP_ERR_FORMAT = "*V{obj_id} "
    QUERY_VALUE_RESP_FORMAT = "=V{obj_id} "

    # error codes
    ERROR_CODES = {
        0: "no error",
        1: "Invalid command for object ID",
        2: "Invalid query/command",
        3: "Missing parameter",
        4: "Parameter out of range",
        5: "Invalid command in startup stage",
        6: "Data checksum error",
        7: "EEPROM read or write error",
        8: "Operation took too long",
        9: "Invalid config ID"
    }

    # priority states
    PRIORITY_STATES = {
        0: "OK",
        1: "warning",
        2: "alarm",
        3: "alarm"
    }

    # alert IDs
    ALERT_IDS = {
        0: "No Alert",
        1: "ADC Fault",
        2: "ADC Not Read",
        3: "Over Range",
        4: "Under Range",
        5: "ADC Invalid",
        6: "No Gauge",
        7: "Unknown",
        8: "Not Supported",
        9: "New ID",
        10: "Over Range",
        11: "Under Range",
        12: "Over Range",
        13: "Ion Em Timeout",
        14: "Not Struck",
        15: "Filament Fail",
        16: "Mag Fail",
        17: "Striker Fail",
        18: "Not Struck",
        19: "Filament Fail",
        20: "Cal Error",
        21: "Initialising",
        22: "Emission Error",
        23: "Over Pressure",
        24: "ASG Cant Zero",
        25: "RampUp Timeout",
        26: "Droop Timeout",
        27: "Run Hours High",
        28: "SC Interlock",
        29: "ID Volts Error",
        30: "Serial ID Fail",
        31: "Upload Active",
        32: "DX Fault",
        33: "Temp Alert",
        34: "SYSI Inhibit",
        35: "Ext Inhibit",
        36: "Temp Inhibit",
        37: "No Reading",
        38: "No Message",
        39: "NOV Failure",
        40: "Upload Timeout",
        41: "Download Failed",
        42: "No Tube",
        43: "Use Gauges 4-6",
        44: "Degas Inhibited",
        45: "IGC Inhibited",
        46: "Brownout/Short",
        47: "Service due"
    }

    # pump states
    PUMP_STATES = {
        0: "Stopped",
        1: "Starting Delay",
        2: "Stopping Short Delay",
        3: "Stopping Normal Delay",
        4: "Running",
        5: "Accelerating",
        6: "Fault Braking",
        7: "Braking"
    }

    # gauge states
    GAUGE_STATES = {
        0: "Gauge Not connected",
        1: "Gauge Connected",
        2: "New Gauge ID",
        3: "Gauge Change",
        4: "Gauge In Alert",
        5: "Off",
        6: "Striking",
        7: "Initialising",
        8: "Calibrating",
        9: "Zeroing",
        10: "Degrassing",
        11: "On",
        12: "Inhibited"
    }

    # unit types
    UNIT_TYPES = {
        66: "V",
        59: "Pa",
        81: "%"
    }

    # object IDs
    TIC_STATUS = 902
    TURBO_PUMP = 904
    TURBO_SPEED = 905
    TURBO_POWER = 906
    BACKING_PUMP = 910
    BACKING_SPEED = 911
    BACKING_POWER = 912
    PRESSURE_GAUGE_1 = 913
    PRESSURE_GAUGE_2 = 914

    def __init__(self,
                 context: QMI_Context,
                 name: str,
                 transport: str
                 ) -> None:
        """Initialise driver.

        Parameters:
            transport:  QMI transport descriptor to connect to the instrument.
        """
        super().__init__(context, name)
        self._timeout = self.DEFAULT_RESPONSE_TIMEOUT
        self._transport_str = transport
        self._transport = create_transport(transport)
        self._scpi_protocol = ScpiProtocol(self._transport,
                                           command_terminator="\r",
                                           response_terminator="\r",
                                           default_timeout=self._timeout)

    def _parse_response(self, raw_response: str) -> str:
        """
        Parse the received response by doing a pattern check and extracting the message string

        Parameters:
            raw_response: the raw response received from the instrument.

        Returns:
            the message sent by the instrument
        """
        response_data = raw_response.split(" ", 1)[1]
        # match the first 2 characters of the string to find what type of response it is
        err_resp_pattern = "[*][SCV]"
        response_pattern = "[=][SCV]"
        if re.match(err_resp_pattern, raw_response) is not None:
            err_code = int(response_data)
            if err_code != 0:
                raise QMI_InstrumentException(f"Error {self.ERROR_CODES[err_code]}")
            return response_data
        elif re.match(response_pattern, raw_response) is None:
            raise QMI_InstrumentException("The response format did not match any valid response formats")
        return response_data

    def _get_pump_status(self, obj_id: int) -> Dict[str, str]:
        """
        Get the status of the pump.

        Parameters:
            obj_id: the object id to send the message to.

        Returns:
            dictionary containing the state, alert and priority
        """
        _logger.info("Getting pump status for instrument [%s]", self._name)
        cmd = self.QUERY_VALUE_CMD_FORMAT.format(obj_id=obj_id)
        resp = [int(x) for x in self._parse_response(self._scpi_protocol.ask(cmd)).split(";")]
        return {
            "Pump state": self.PUMP_STATES[resp[0]],
            "Alert": self.ALERT_IDS[resp[1]],
            "Priority": self.PRIORITY_STATES[resp[2]]
        }

    def _get_pump_speed(self, obj_id: int) -> Dict[str, str]:
        """
        Get the speed of the pump as a percentage of the maximum speed.

        Parameters:
            obj_id: the object id to send the message to.

        Returns:
            relative value of speed compared to maximum speed.
        """
        _logger.info("Getting the pump speed for instrument [%s]", self._name)
        cmd = self.QUERY_VALUE_CMD_FORMAT.format(obj_id=obj_id)
        resp = self._parse_response(self._scpi_protocol.ask(cmd)).split(";")
        return {
            "Pump speed": resp[0],
            "Alert": self.ALERT_IDS[int(resp[1])],
            "Priority": self.PRIORITY_STATES[int(resp[2])]
        }

    def _turn_on_off_pump(self, obj_id: int, on_off: int) -> None:
        """
        Turn on the pump.

        Parameters:
            obj_id: the object id to send the message to.
        """
        cmd = self.GENERAL_CMD_FORMAT.format(obj_id=obj_id, msg=on_off)
        self._parse_response(self._scpi_protocol.ask(cmd))

    def _get_pump_power(self, obj_id: int) -> Dict[str, str]:
        """
        Get the power of the pump.

        Parameters:
            obj_id: the object to send the message to.

        Returns:
            pump power in Watts.
        """
        _logger.info("Getting pump power for instrument [%s]", self._name)
        cmd = self.QUERY_VALUE_CMD_FORMAT.format(obj_id=obj_id)
        resp = self._parse_response(self._scpi_protocol.ask(cmd)).split(";")
        return {
            "Pump power": resp[0],
            "Alert": self.ALERT_IDS[int(resp[1])],
            "Priority": self.PRIORITY_STATES[int(resp[2])]
        }

    def _get_pressure(self, obj_id: int) -> Dict[str, str]:
        """
        Get the pressure from a gauge.

        Parameters:
            obj_id: the object to send the message to.

        Returns:
            dictionary with pressure, units type, alert, priority and state.
        """
        cmd = self.QUERY_VALUE_CMD_FORMAT.format(obj_id=obj_id)
        resp = self._parse_response(self._scpi_protocol.ask(cmd)).split(";")
        return {
            "Pressure": resp[0],
            "Unit": self.UNIT_TYPES[int(resp[1])],
            "State": self.GAUGE_STATES[int(resp[2])],
            "Alert": self.ALERT_IDS[int(resp[3])],
            "Priority": self.PRIORITY_STATES[int(resp[4])]
        }

    @rpc_method
    def open(self) -> None:
        _logger.info("Opening connection instrument [%s]", self._name)
        self._check_is_closed()
        self._transport.open()
        super().open()

    @rpc_method
    def close(self) -> None:
        _logger.info("Closing connection to instrument [%s]", self._name)
        self._check_is_open()
        self._transport.close()
        super().close()

    @rpc_method
    def get_idn(self) -> QMI_InstrumentIdentification:
        """
        Read instrument type and version and return QMI_InstrumentIdentification instance.

        Returns:
            instrument identification
        """
        _logger.info("Getting info for instrument [%s]", self._name)
        cmd = self.QUERY_SETUP_CMD_FORMAT.format(obj_id=self.TIC_STATUS)
        instr_info = self._parse_response(self._scpi_protocol.ask(cmd)).split(";")
        return QMI_InstrumentIdentification(vendor="Edwards",
                                            model=instr_info[0],
                                            version=instr_info[1],
                                            serial=instr_info[2])

    @rpc_method
    def get_tic_status(self) -> Dict[str, str]:
        """
        Get the status of the turbo pump, backing pump and pressure gauge
        attached to the TIC.

        Returns:
            dictionary where the key is the equipment and the value is its state
        """
        _logger.info("Getting status for instrument [%s]", self._name)
        cmd = self.QUERY_VALUE_CMD_FORMAT.format(obj_id=self.TIC_STATUS)
        resp = [int(x) for x in self._parse_response(self._scpi_protocol.ask(cmd)).split(";")]
        return {
            "Turbo pump state": self.PUMP_STATES[resp[0]],
            "Backing pump state": self.PUMP_STATES[resp[1]],
            "Gauge 2": self.GAUGE_STATES[resp[2]],
            "Alert": self.ALERT_IDS[resp[3]],
            "Priority": self.PRIORITY_STATES[resp[4]]
        }

    @rpc_method
    def get_turbo_pump_status(self) -> Dict[str, str]:
        """
        Get the status of the turbo pump.

        Returns:
            dictionary containing the state, alert and priority
        """
        return self._get_pump_status(self.TURBO_PUMP)

    @rpc_method
    def get_backing_pump_status(self) -> Dict[str, str]:
        """
        Get the status of the backing pump.

        Returns:
            dictionary containing the state, alert and priority
        """
        return self._get_pump_status(self.BACKING_PUMP)

    @rpc_method
    def turn_on_turbo_pump(self) -> None:
        """
        Turn on the turbo pump.
        """
        _logger.info("Turning on the turbo pump for instrument [%s]", self._name)
        self._turn_on_off_pump(self.TURBO_PUMP, 1)

    @rpc_method
    def turn_off_turbo_pump(self) -> None:
        """
        Turn off the turbo pump.
        """
        _logger.info("Turning off the turbo pump for instrument [%s]", self._name)
        self._turn_on_off_pump(self.TURBO_PUMP, 0)

    @rpc_method
    def turn_on_backing_pump(self) -> None:
        """
        Turn on the turbo pump.
        """
        _logger.info("Turning on the backing pump for instrument [%s]", self._name)
        self._turn_on_off_pump(self.BACKING_PUMP, 1)

    @rpc_method
    def turn_off_backing_pump(self) -> None:
        """
        Turn off the turbo pump.
        """
        _logger.info("Turning off the backing pump for instrument [%s]", self._name)
        self._turn_on_off_pump(self.BACKING_PUMP, 0)

    @rpc_method
    def get_turbo_pump_speed(self) -> Dict[str, str]:
        """
        Get the speed of the turbo pump as a percentage of the maximum speed.

        Returns:
            relative value of speed compared to maximum speed.
        """
        return self._get_pump_speed(self.TURBO_SPEED)

    @rpc_method
    def get_backing_pump_speed(self) -> Dict[str, str]:
        """
        Get the speed of the backing pump as a percentage of the maximum speed.

        Returns:
            relative value of speed compared to maximum speed.
        """
        return self._get_pump_speed(self.BACKING_SPEED)

    @rpc_method
    def get_turbo_pump_power(self) -> Dict[str, str]:
        """
        Get the power of the turbo pump.

        Returns:
            turbo pump power in Watts.
        """
        return self._get_pump_power(self.TURBO_POWER)

    @rpc_method
    def get_backing_pump_power(self) -> Dict[str, str]:
        """
        Get the power of the backing pump.

        Returns:
            backing pump power in Watts.
        """
        return self._get_pump_power(self.BACKING_POWER)

    @rpc_method
    def get_pressure_gauge_1(self) -> Dict[str, str]:
        """
        Get the pressure from Gauge 1.

        Returns:
            dictionary with pressure, units type, alert, priority and state.
        """
        _logger.info("Getting pressure from gauge 1 for instrument [%s]", self._name)
        return self._get_pressure(self.PRESSURE_GAUGE_1)

    @rpc_method
    def get_pressure_gauge_2(self) -> Dict[str, str]:
        """
        Get the pressure from Gauge 2.

        Returns:
            dictionary with pressure, units type, alert, priority and state.
        """
        _logger.info("Getting pressure from gauge 2 for instrument [%s]", self._name)
        return self._get_pressure(self.PRESSURE_GAUGE_2)
