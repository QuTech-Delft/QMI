"""Instrument driver for the Montana Cryostation S50."""

from qmi.instruments.montana._cryostation_rest import (
    Montana_CryostationRest_Base,
    Montana_CryostationRest_Heater_Properties,
    Montana_CryostationRest_System_Goal,
    Montana_CryostationRest_System_State,
    Montana_CryostationRest_Thermometer_Properties,
)

# Model-specific names of the shared REST API data types.
Montana_CryostationS50_Thermometer_Properties = Montana_CryostationRest_Thermometer_Properties
Montana_CryostationS50_Heater_Properties = Montana_CryostationRest_Heater_Properties
Montana_CryostationS50_System_State = Montana_CryostationRest_System_State
Montana_CryostationS50_System_Goal = Montana_CryostationRest_System_Goal


class Montana_CryostationS50(Montana_CryostationRest_Base):
    """Instrument driver for the Montana Cryostation S50.

    The S50 uses a RESTful API for communication. All RPC methods are implemented in the common base class
    `qmi.instruments.montana._cryostation_rest.Montana_CryostationRest_Base`.
    """
