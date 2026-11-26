"""Instrument driver for the Montana Cryostation S100."""

import logging

from qmi.core.rpc import rpc_method
from qmi.instruments.montana._cryostation_rest import (
    Montana_CryostationRest_Base,
    Montana_CryostationRest_Heater_Properties,
    Montana_CryostationRest_System_Goal,
    Montana_CryostationRest_System_State,
    Montana_CryostationRest_Thermometer_Properties,
)

# Global variable holding the logger for this module.
_logger = logging.getLogger(__name__)

# Model-specific names of the shared REST API data types.
Montana_CryostationS100_Thermometer_Properties = Montana_CryostationRest_Thermometer_Properties
Montana_CryostationS100_Heater_Properties = Montana_CryostationRest_Heater_Properties
Montana_CryostationS100_System_State = Montana_CryostationRest_System_State
Montana_CryostationS100_System_Goal = Montana_CryostationRest_System_Goal


class Montana_CryostationS100(Montana_CryostationRest_Base):
    """Instrument driver for the Montana Cryostation S100.

    The S100 uses the same RESTful API as the S50. Next to the RPC methods of the common base class
    `qmi.instruments.montana._cryostation_rest.Montana_CryostationRest_Base`, this driver provides
    convenience methods that return single values of the thermometers and heaters.
    """

    # Aliases of the subsystem strings, as named in this driver.
    SAMPLE_CHAMBER_TEMP_CONTROLLER_PLATFORM_SUBSYSTEM_STR = (
        Montana_CryostationRest_Base.SAMPLE_CHAMBER_TEMP_CONTROLLER_SUBSYSTEM_STR
    )
    SAMPLE_CHAMBER_TEMP_CONTROLLER_CRYOOPTIC_SUBSYSTEM_STR = (
        Montana_CryostationRest_Base.CRYOOPTIC_TEMP_CONTROLLER_SUBSYSTEM_STR
    )

    @rpc_method
    def get_platform_thermometer_properties(self) -> Montana_CryostationS100_Thermometer_Properties:
        """Get the platform thermometer properties. Same as `get_sample_thermometer_properties`.

        Returns:
            Dataclass with the properties.
        """
        _logger.info("Getting thermometer properties for platform for %s", self._name)
        return self._get_thermometer_properties(self.SAMPLE_CHAMBER_TEMP_CONTROLLER_SUBSYSTEM_STR)

    @rpc_method
    def get_cryo_optic_thermometer_properties(self) -> Montana_CryostationS100_Thermometer_Properties:
        """Get the cryo-optic thermometer properties. Same as `get_cryooptic_thermometer_properties`.

        Returns:
            Dataclass with the properties.
        """
        _logger.info("Getting thermometer properties for cryoOptic for %s", self._name)
        return self._get_thermometer_properties(self.CRYOOPTIC_TEMP_CONTROLLER_SUBSYSTEM_STR)

    @rpc_method
    def get_cryo_optic_heater_properties(self) -> Montana_CryostationS100_Heater_Properties:
        """Get the cryo-optic heater properties. Same as `get_cryooptic_heater_properties`.

        Returns:
            Dataclass with the properties.
        """
        _logger.info("Getting heater properties for cryoOptic for %s", self._name)
        return self._get_heater_properties(self.CRYOOPTIC_TEMP_CONTROLLER_SUBSYSTEM_STR)

    @rpc_method
    def get_platform_heater_power(self) -> float:
        """Get the platform heater power.

        Returns:
            Heater power in Watt.
        """
        _logger.info("Getting heater power for platform for %s", self._name)
        return self._get_heater_properties(self.SAMPLE_CHAMBER_TEMP_CONTROLLER_SUBSYSTEM_STR).power

    @rpc_method
    def get_platform_temperature(self) -> float:
        """Get the platform temperature.

        Returns:
            Temperature in Kelvin.
        """
        _logger.info("Getting temperature for platform for %s", self._name)
        return self._get_thermometer_properties(self.SAMPLE_CHAMBER_TEMP_CONTROLLER_SUBSYSTEM_STR).temperature

    @rpc_method
    def get_platform_stability(self) -> float:
        """Get the platform temperature stability.

        Returns:
            Temperature stability in Kelvin.
        """
        _logger.info("Getting temperature stability for platform for %s", self._name)
        return self._get_thermometer_properties(
            self.SAMPLE_CHAMBER_TEMP_CONTROLLER_SUBSYSTEM_STR
        ).temperature_stability

    @rpc_method
    def get_stage1_temperature(self) -> float:
        """Get the stage 1 temperature.

        Returns:
            Temperature in Kelvin.
        """
        _logger.info("Getting temperature for stage1 for %s", self._name)
        return self._get_thermometer_properties(self.COOLER_TEMP_CONTROLLER_SUBSYSTEM_STR + "/stage1").temperature

    @rpc_method
    def get_stage2_temperature(self) -> float:
        """Get the stage 2 temperature.

        Returns:
            Temperature in Kelvin.
        """
        _logger.info("Getting temperature for stage2 for %s", self._name)
        return self._get_thermometer_properties(self.COOLER_TEMP_CONTROLLER_SUBSYSTEM_STR + "/stage2").temperature

    @rpc_method
    def get_cryo_optic_temperature(self) -> float:
        """Get the cryo-optic temperature.

        Returns:
            Temperature in Kelvin.
        """
        _logger.info("Getting temperature for cryoOptic for %s", self._name)
        return self._get_thermometer_properties(self.CRYOOPTIC_TEMP_CONTROLLER_SUBSYSTEM_STR).temperature

    @rpc_method
    def get_cryo_optic_heater_power(self) -> float:
        """Get the cryo-optic heater power.

        Returns:
            Heater power in Watt.
        """
        _logger.info("Getting heater power for cryoOptic for %s", self._name)
        return self._get_heater_properties(self.CRYOOPTIC_TEMP_CONTROLLER_SUBSYSTEM_STR).power

    @rpc_method
    def get_cryo_optic_stability(self) -> float:
        """Get the cryo-optic temperature stability.

        Returns:
            Temperature stability in Kelvin.
        """
        _logger.info("Getting temperature stability for cryoOptic for %s", self._name)
        return self._get_thermometer_properties(self.CRYOOPTIC_TEMP_CONTROLLER_SUBSYSTEM_STR).temperature_stability
