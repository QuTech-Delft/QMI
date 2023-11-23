"""
Instrument driver for the Edwards Turbo Instrument Controller.
"""
from enum import Enum
import logging
import re
from typing import Dict, NamedTuple, Tuple

from qmi.core.context import QMI_Context
from qmi.core.exceptions import QMI_InstrumentException
from qmi.core.instrument import QMI_Instrument, QMI_InstrumentIdentification
from qmi.core.rpc import rpc_method
from qmi.core.scpi_protocol import ScpiProtocol
from qmi.core.transport import create_transport


# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

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


class EdwardsVacuum_TIC_ErrorCode(Enum):
    """
    Error code for the instrument.
    """
    NO_ERROR = 0
    INVALID_COMMAND_FOR_OBJECT_ID = 1
    INVALID_QUERY_OR_COMMAND = 2
    MISSING_PARAMETER = 3
    PARAMETER_OUT_OF_RANGE = 4
    INVALID_COMMAND_IN_STARTUP_STAGE = 5
    DATA_CHECKSUM_ERROR = 6
    EEPROM_READ_OR_WRITE_ERROR = 7
    OPERATION_TOOK_TOO_LONG = 8
    INVALID_CONFIG_ID = 9


class EdwardsVacuum_TIC_Priority(Enum):
    """
    Priority level for instrument.
    """
    OK = 0
    WARNING = 1
    ALARM = 2
    ALARM_2 = 3


class EdwardsVacuum_TIC_AlertId(Enum):
    """
    Alert ID for instrument.
    """
    NO_ALERT = 0
    ADC_FAULT = 1
    ADC_NOT_READ = 2
    OVER_RANGE = 3
    UNDER_RANGE = 4
    ADC_INVALID = 5
    NO_GAUGE = 6
    UNKNOWN = 7
    NOT_SUPPORTED = 8
    NEW_ID = 9
    OVER_RANGE_2 = 10
    UNDER_RANGE_2 = 11
    OVER_RANGE_3 = 12
    ION_EM_TIMEOUT = 13
    NOT_STRUCK = 14
    FILAMENT_FAIL = 15
    MAG_FAIL = 16
    STRIKER_FAIL = 17
    NOT_STUCK = 18
    FILAMENT_FAIL_2 = 19
    CAL_ERROR = 20
    INITIALISING = 21
    EMISSION_ERROR = 22
    OVER_PRESSURE = 23
    ASG_CANT_ZERO = 24
    RAMPUP_TIMEOUT = 25
    DROOP_TIMEOUT = 26
    RUN_HOURS_HIGH = 27
    SC_INTERLOCK = 28
    ID_VOLTS_ERROR = 29
    SERIAL_ID_FAIL = 30
    UPLOAD_ACTIVE = 31
    DX_FAULT = 32
    TEMP_ALERT = 33
    SYSI_INHIBIT = 34
    EXT_INHIBIT = 35
    TEMP_INHIBIT = 36
    NO_READING = 37
    NO_MESSAGE = 38
    NOV_FAILURE = 39
    UPLOAD_TIMEOUT = 40
    DOWNLOAD_FAILED = 41
    NO_TUBE = 42
    USE_GAUGES_4_TO_6 = 43
    DEGAS_INHIBITED = 44
    IGC_INHIBITED = 45
    BROWNOUT_OR_SHORT = 46
    SERVICE_DUE = 47


class EdwardsVacuum_TIC_State(Enum):
    """
    State of a device in the instrument.
    """
    OFF = 0
    OFF_GOING_ON = 1
    ON_GOING_OFF_SHUTDOWN = 2
    ON_GOING_OFF_NORMAL = 3
    ON = 4


class EdwardsVacuum_TIC_PumpState(Enum):
    """
    Pump state of instrument.
    """
    STOPPED = 0
    STARTING_DELAY = 1
    STOPPING_SHORT_DELAY = 2
    STOPPING_NORMAL_DELAY = 3
    RUNNING = 4
    ACCELERATING = 5
    FAULT_BRAKING = 6
    BRAKING = 7


class EdwardsVacuum_TIC_GaugeState(Enum):
    """
    Gauge state of the instrument.
    """
    GAUGE_NOT_CONNECTED = 0
    GAUGE_CONNECTED = 1
    NEW_GAUGE_ID = 2
    GAUGE_CHANGED = 3
    GAUGE_IN_ALERT = 4
    OFF = 5
    STRIKING = 6
    INITIALISING = 7
    CALIBRATING = 8
    ZEROING = 9
    DEGASSING = 10
    ON = 11
    INHIBITED = 12


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
SYSTEM = 933

PRESSURE_GAUGE_MAP = {
    1: 913,
    2: 914,
    3: 915
}

RELAY_MAP = {
    1: 916,
    2: 917,
    3: 918
}


class EdwardsVacuum_TIC_PumpStateResponse(NamedTuple):
    """
    State of the pump.

    Attributes:
        state:      State of the pump.
        alert:      Alert given by the system.
        priority:   Priority level of the system.
    """
    state: EdwardsVacuum_TIC_PumpState
    alert: EdwardsVacuum_TIC_AlertId
    priority: EdwardsVacuum_TIC_Priority


class EdwardsVacuum_TIC_PumpSpeedResponse(NamedTuple):
    """
    Speed of the pump.

    Attributes:
        speed:      Speed as a percentage of the maximum value [0-100%].
        alert:      Alert given by the system.
        priority:   Priority level of the system.
    """
    speed: float
    alert: EdwardsVacuum_TIC_AlertId
    priority: EdwardsVacuum_TIC_Priority


class EdwardsVacuum_TIC_PumpPowerResponse(NamedTuple):
    """
    Speed of the pump.

    Attributes:
        power:      Power of the pump in Watts.
        alert:      Alert given by the system.
        priority:   Priority level of the system.
    """
    power: float
    alert: EdwardsVacuum_TIC_AlertId
    priority: EdwardsVacuum_TIC_Priority


class EdwardsVacuum_TIC_GaugePressureResponse(NamedTuple):
    """
    Pressure read by the gauge.

    Attributes:
        pressure:   Pressure.
        unit:       Unit of the value.
        state:      State of the gauge.
        alert:      Alert given by the system.
        priority:   Priority level of the system.
    """
    pressure: float
    unit: str
    state: EdwardsVacuum_TIC_GaugeState
    alert: EdwardsVacuum_TIC_AlertId
    priority: EdwardsVacuum_TIC_Priority


class EdwardsVacuum_TIC_StateResponse(NamedTuple):
    """
    State of a device of the instrument.

    Attributes:
        state:      State of the device.
        alert:      Alert given by the system.
        priority:   Priority level of the system.
    """
    state: EdwardsVacuum_TIC_State
    alert: EdwardsVacuum_TIC_AlertId
    priority: EdwardsVacuum_TIC_Priority


class EdwardsVacuum_TIC_StatusResponse(NamedTuple):
    """
    Status of the instument.

    Attributes:
        turbo_pump_state:   State of the turbo pump.
        backing_pump_state: State of the backing pump.
        gauge_1_state:      State of gauge 1.
        gauge_2_state:      State of gauge 2.
        gauge_3_state:      State of gauge 3.
        relay_1_state:      State of relay 1.
        relay_2_state:      State of relay 2.
        relay_3_state:      State of relay 3.
        alert:              Alert given by the system.
        priority:           Priority level of the system.
    """
    turbo_pump_state: EdwardsVacuum_TIC_PumpState
    backing_pump_state: EdwardsVacuum_TIC_PumpState
    gauge_1_state: EdwardsVacuum_TIC_GaugeState
    gauge_2_state: EdwardsVacuum_TIC_GaugeState
    gauge_3_state: EdwardsVacuum_TIC_GaugeState
    relay_1_state: EdwardsVacuum_TIC_State
    relay_2_state: EdwardsVacuum_TIC_State
    relay_3_state: EdwardsVacuum_TIC_State
    alert: EdwardsVacuum_TIC_AlertId
    priority: EdwardsVacuum_TIC_Priority


class EdwardsVacuum_TIC_SystemOnOffSetupConfigResponse(NamedTuple):
    """
    System on/off setup config of the instrument.

    Attributes:
        turbo_pump_setup:   On/off setup config of the turbo pump. First entry of tuple is the on config and
                            second is the off config.
        backing_pump_setup: On/off setup config of the backing pump. First entry of tuple is the on config and
                            second is the off config.
        gauge_1_setup:      On/off setup config of gauge 1. First entry of tuple is the on config and
                            second is the off config.
        gauge_2_setup:      On/off setup config of gauge 2. First entry of tuple is the on config and
                            second is the off config.
        gauge_3_setup:      On/off setup config of gauge 3. First entry of tuple is the on config and
                            second is the off config.
        relay_1_setup:      On/off setup config of relay 1. First entry of tuple is the on config and
                            second is the off config.
        relay_2_setup:      On/off setup config of relay 2. First entry of tuple is the on config and
                            second is the off config.
        relay_3_setup:      On/off setup config of relay 3. First entry of tuple is the on config and
                            second is the off config.
    """
    turbo_pump_setup: Tuple[bool, bool]
    backing_pump_setup: Tuple[bool, bool]
    gauge_1_setup: Tuple[bool, bool]
    gauge_2_setup: Tuple[bool, bool]
    gauge_3_setup: Tuple[bool, bool]
    relay_1_setup: Tuple[bool, bool]
    relay_2_setup: Tuple[bool, bool]
    relay_3_setup: Tuple[bool, bool]


class Edwards_TurboInstrumentController(QMI_Instrument):
    """Instrument driver for the Edwards Turbo Instrument Controller."""

    # default response timeout in seconds
    DEFAULT_RESPONSE_TIMEOUT = 5.0

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
            raw_response: The raw response received from the instrument.

        Returns:
            Message sent by the instrument.
        """
        resp, response_data = raw_response.split(" ", 1)
        # match the first 2 characters of the string to find what type of response it is
        err_resp_pattern = "[*][SCV]"
        response_pattern = "[=][SCV]"
        if re.match(err_resp_pattern, raw_response) is not None:
            err_code = int(response_data)
            if err_code != 0:
                # when the response is *C with a code of 1, that is not an error, but a response
                if not (err_code == 1 and resp[1] == "C"):
                    raise QMI_InstrumentException(f"Error {EdwardsVacuum_TIC_ErrorCode(err_code)}")
            return response_data
        elif re.match(response_pattern, raw_response) is None:
            raise QMI_InstrumentException("The response format did not match any valid response formats")
        return response_data

    def _get_pump_state(self, obj_id: int) -> EdwardsVacuum_TIC_PumpStateResponse:
        """
        Get the state of the pump.

        Parameters:
            obj_id: The object id to send the message to.

        Returns:
            An instance of EdwardsVacuum_TIC_PumpStateResponse.
        """
        _logger.info("Getting pump status for instrument [%s]", self._name)
        cmd = QUERY_VALUE_CMD_FORMAT.format(obj_id=obj_id)
        resp = [int(x) for x in self._parse_response(self._scpi_protocol.ask(cmd)).split(";")]
        return EdwardsVacuum_TIC_PumpStateResponse(
            state=EdwardsVacuum_TIC_PumpState(resp[0]),
            alert=EdwardsVacuum_TIC_AlertId(resp[1]),
            priority=EdwardsVacuum_TIC_Priority(resp[2])
        )

    def _get_pump_speed(self, obj_id: int) -> EdwardsVacuum_TIC_PumpSpeedResponse:
        """
        Get the speed of the pump as a percentage of the maximum speed.

        Parameters:
            obj_id: The object id to send the message to.

        Returns:
            An instance of EdwardsVacuum_TIC_PumpSpeedResponse.
        """
        _logger.info("Getting the pump speed for instrument [%s]", self._name)
        cmd = QUERY_VALUE_CMD_FORMAT.format(obj_id=obj_id)
        resp = self._parse_response(self._scpi_protocol.ask(cmd)).split(";")
        return EdwardsVacuum_TIC_PumpSpeedResponse(
            speed=float(resp[0]),
            alert=EdwardsVacuum_TIC_AlertId(int(resp[1])),
            priority=EdwardsVacuum_TIC_Priority(int(resp[2]))
        )

    def _turn_on_off(self, obj_id: int, on_off: bool) -> None:
        """
        Turn on or off an object.

        Parameters:
            obj_id: The object id to send the message to.
            on_off: False means off and True means on.
        """
        cmd = GENERAL_CMD_FORMAT.format(obj_id=obj_id, msg=int(on_off))
        self._parse_response(self._scpi_protocol.ask(cmd))

    def _get_pump_power(self, obj_id: int) -> EdwardsVacuum_TIC_PumpPowerResponse:
        """
        Get the power of the pump.

        Parameters:
            obj_id: The object to send the message to.

        Returns:
            An instance of EdwardsVacuum_TIC_PumpPowerResponse.
        """
        _logger.info("Getting pump power for instrument [%s]", self._name)
        cmd = QUERY_VALUE_CMD_FORMAT.format(obj_id=obj_id)
        resp = self._parse_response(self._scpi_protocol.ask(cmd)).split(";")
        return EdwardsVacuum_TIC_PumpPowerResponse(
            power=float(resp[0]),
            alert=EdwardsVacuum_TIC_AlertId(int(resp[1])),
            priority=EdwardsVacuum_TIC_Priority(int(resp[2]))
        )

    def _get_pressure(self, obj_id: int) -> EdwardsVacuum_TIC_GaugePressureResponse:
        """
        Get the pressure from a gauge.

        Parameters:
            obj_id: The object to send the message to.

        Returns:
            An instance of EdwardsVacuum_TIC_GaugePressureResponse.
        """
        cmd = QUERY_VALUE_CMD_FORMAT.format(obj_id=obj_id)
        resp = self._parse_response(self._scpi_protocol.ask(cmd)).split(";")
        return EdwardsVacuum_TIC_GaugePressureResponse(
            pressure=float(resp[0]),
            unit=UNIT_TYPES[int(resp[1])],
            state=EdwardsVacuum_TIC_GaugeState(int(resp[2])),
            alert=EdwardsVacuum_TIC_AlertId(int(resp[3])),
            priority=EdwardsVacuum_TIC_Priority(int(resp[4]))
        )

    def _get_state(self, obj_id: int) -> EdwardsVacuum_TIC_StateResponse:
        """
        Get the state of the provided object id.

        Parameters:
            obj_id: The object id.

        Returns:
            An instance of EdwardsVacuum_TIC_StateResponse.
        """
        cmd = QUERY_VALUE_CMD_FORMAT.format(obj_id=obj_id)
        resp = self._parse_response(self._scpi_protocol.ask(cmd)).split(";")
        return EdwardsVacuum_TIC_StateResponse(
            state=EdwardsVacuum_TIC_State(int(resp[0])),
            alert=EdwardsVacuum_TIC_AlertId(int(resp[1])),
            priority=EdwardsVacuum_TIC_Priority(int(resp[2]))
        )

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
            Instrument identification.
        """
        _logger.info("Getting info for instrument [%s]", self._name)
        cmd = QUERY_SETUP_CMD_FORMAT.format(obj_id=TIC_STATUS)
        instr_info = self._parse_response(self._scpi_protocol.ask(cmd)).split(";")
        return QMI_InstrumentIdentification(vendor="Edwards",
                                            model=instr_info[0],
                                            version=instr_info[1],
                                            serial=instr_info[2])

    @rpc_method
    def get_tic_status(self) -> EdwardsVacuum_TIC_StatusResponse:
        """
        Get the status of the turbo pump, backing pump and pressure gauge
        attached to the TIC.

        Returns:
            An instance of EdwardsVacuum_TIC_StatusResponse.
        """
        _logger.info("Getting status for instrument [%s]", self._name)
        cmd = QUERY_VALUE_CMD_FORMAT.format(obj_id=TIC_STATUS)
        resp = [int(x) for x in self._parse_response(self._scpi_protocol.ask(cmd)).split(";")]
        return EdwardsVacuum_TIC_StatusResponse(
            turbo_pump_state=EdwardsVacuum_TIC_PumpState(resp[0]),
            backing_pump_state=EdwardsVacuum_TIC_PumpState(resp[1]),
            gauge_1_state=EdwardsVacuum_TIC_GaugeState(resp[2]),
            gauge_2_state=EdwardsVacuum_TIC_GaugeState(resp[3]),
            gauge_3_state=EdwardsVacuum_TIC_GaugeState(resp[4]),
            relay_1_state=EdwardsVacuum_TIC_State(resp[5]),
            relay_2_state=EdwardsVacuum_TIC_State(resp[6]),
            relay_3_state=EdwardsVacuum_TIC_State(resp[7]),
            alert=EdwardsVacuum_TIC_AlertId(resp[8]),
            priority=EdwardsVacuum_TIC_Priority(resp[9])
        )

    @rpc_method
    def get_turbo_pump_state(self) -> EdwardsVacuum_TIC_PumpStateResponse:
        """
        Get the state of the turbo pump.

        Returns:
            An instance of EdwardsVacuum_TIC_PumpStateResponse.
        """
        return self._get_pump_state(TURBO_PUMP)

    @rpc_method
    def get_backing_pump_state(self) -> EdwardsVacuum_TIC_PumpStateResponse:
        """
        Get the state of the backing pump.

        Returns:
            An instance of EdwardsVacuum_TIC_PumpStateResponse.
        """
        return self._get_pump_state(BACKING_PUMP)

    @rpc_method
    def turn_on_turbo_pump(self) -> None:
        """
        Turn on the turbo pump.
        """
        _logger.info("Turning on the turbo pump for instrument [%s]", self._name)
        self._turn_on_off(TURBO_PUMP, True)

    @rpc_method
    def turn_off_turbo_pump(self) -> None:
        """
        Turn off the turbo pump.
        """
        _logger.info("Turning off the turbo pump for instrument [%s]", self._name)
        self._turn_on_off(TURBO_PUMP, False)

    @rpc_method
    def turn_on_backing_pump(self) -> None:
        """
        Turn on the turbo pump.
        """
        _logger.info("Turning on the backing pump for instrument [%s]", self._name)
        self._turn_on_off(BACKING_PUMP, True)

    @rpc_method
    def turn_off_backing_pump(self) -> None:
        """
        Turn off the turbo pump.
        """
        _logger.info("Turning off the backing pump for instrument [%s]", self._name)
        self._turn_on_off(BACKING_PUMP, False)

    @rpc_method
    def get_turbo_pump_speed(self) -> EdwardsVacuum_TIC_PumpSpeedResponse:
        """
        Get the speed of the turbo pump as a percentage of the maximum speed.

        Returns:
            An instance of EdwardsVacuum_TIC_PumpSpeedResponse.
        """
        return self._get_pump_speed(TURBO_SPEED)

    @rpc_method
    def get_backing_pump_speed(self) -> EdwardsVacuum_TIC_PumpSpeedResponse:
        """
        Get the speed of the backing pump as a percentage of the maximum speed.

        Returns:
            An instance of EdwardsVacuum_TIC_PumpStateResponse.
        """
        return self._get_pump_speed(BACKING_SPEED)

    @rpc_method
    def get_turbo_pump_power(self) -> EdwardsVacuum_TIC_PumpPowerResponse:
        """
        Get the power of the turbo pump.

        Returns:
            An instance of EdwardsVacuum_TIC_PumpPowerResponse.
        """
        return self._get_pump_power(TURBO_POWER)

    @rpc_method
    def get_backing_pump_power(self) -> EdwardsVacuum_TIC_PumpPowerResponse:
        """
        Get the power of the backing pump.

        Returns:
            An instance of EdwardsVacuum_TIC_PumpPowerResponse.
        """
        return self._get_pump_power(BACKING_POWER)

    @rpc_method
    def get_pressure(self, gauge_num: int) -> EdwardsVacuum_TIC_GaugePressureResponse:
        """
        Get the pressure from the pressure gauge.

        Parameters:
            gauge_num:  Gauge to address.

        Returns:
            An instance of EdwardsVacuum_TIC_GaugePressureResponse.
        """
        _logger.info("Getting pressure from gauge %s for instrument [%s]", gauge_num, self._name)
        return self._get_pressure(PRESSURE_GAUGE_MAP[gauge_num])

    @rpc_method
    def get_relay_state(self, relay_num: int) -> EdwardsVacuum_TIC_StateResponse:
        """
        Get the state of the relay.

        Parameters:
            relay_num:  Relay to address.

        Returns:
            An instance of EdwardsVacuum_TIC_StateResponse.
        """
        _logger.info("Getting state of relay %s for instrument [%s]", relay_num, self._name)
        return self._get_state(RELAY_MAP[relay_num])

    @rpc_method
    def turn_on_relay(self, relay_num: int) -> None:
        """
        Turn on the relay.

        Parameters:
            relay_num:  Relay to address.
        """
        _logger.info("Turning on relay %s for instrument [%s]", relay_num, self._name)
        self._turn_on_off(RELAY_MAP[relay_num], True)

    @rpc_method
    def turn_off_relay(self, relay_num: int) -> None:
        """
        Turn off the relay.
        """
        _logger.info("Turning off relay %s for instrument [%s]", relay_num, self._name)
        self._turn_on_off(RELAY_MAP[relay_num], False)

    @rpc_method
    def get_system_on_off_setup_config(self) -> EdwardsVacuum_TIC_SystemOnOffSetupConfigResponse:
        """
        Get the on/off setup config of the system.

        Returns:
            An instance of EdwardsVacuum_TIC_SystemOnOffSetupConfigResponse.
        """
        _logger.info("Getting on/off setup config of system for instrument [%s]", self._name)
        cmd = QUERY_SETUP_CMD_FORMAT.format(obj_id=SYSTEM)
        resp = self._parse_response(self._scpi_protocol.ask(cmd)).split(";")
        bool_resp = [bool(int(i)) for i in resp]
        return EdwardsVacuum_TIC_SystemOnOffSetupConfigResponse(
            turbo_pump_setup=(bool_resp[1], bool_resp[2]),
            backing_pump_setup=(bool_resp[4], bool_resp[5]),
            gauge_1_setup=(bool_resp[7], bool_resp[8]),
            gauge_2_setup=(bool_resp[10], bool_resp[11]),
            gauge_3_setup=(bool_resp[13], bool_resp[14]),
            relay_1_setup=(bool_resp[16], bool_resp[17]),
            relay_2_setup=(bool_resp[19], bool_resp[20]),
            relay_3_setup=(bool_resp[22], bool_resp[23]))

    @rpc_method
    def set_system_on_off_setup_config(self, config: Dict[int, Tuple[bool, bool]]) -> None:
        """
        Set the on/off setup config of the system.

        Parameters:
            config: The object to setup. The first entry in the tuple is the object id.
                    the second is a tuple for the on off setup.
        """
        _logger.info("Setting on/off setup config of system for instrument [%s]", self._name)
        data = ""
        for obj_id, setup in config.items():
            data += f"{obj_id};{int(setup[0])};{int(setup[1])};"
        cmd = SETUP_CMD_FORMAT.format(obj_id=SYSTEM, data=data)
        # remove the last ";"" from the string and send that as the command
        self._scpi_protocol.ask(cmd[:-1])

    @rpc_method
    def get_system_state(self) -> EdwardsVacuum_TIC_StateResponse:
        """
        Get the state of the system.

        Returns:
            An instance of EdwardsVacuum_TIC_StateResponse.
        """
        _logger.info("Getting state of system for instrument [%s]", self._name)
        return self._get_state(SYSTEM)

    @rpc_method
    def turn_on_system(self) -> None:
        """
        Turn on the system.
        """
        _logger.info("Turning on system for instrument [%s]", self._name)
        self._turn_on_off(SYSTEM, True)

    @rpc_method
    def turn_off_system(self) -> None:
        """
        Turn off the system.
        """
        _logger.info("Turning off system for instrument [%s]", self._name)
        self._turn_on_off(SYSTEM, False)
