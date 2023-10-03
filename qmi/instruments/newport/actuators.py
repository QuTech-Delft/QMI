"""Actuators for the single axis motion controllers."""
from typing import NamedTuple


class TravelRange(NamedTuple):
    """Travel range """
    min: float
    max: float


class LinearActuator:
    """Linear actuator."""

    def __init__(self,
                 travel_range_min: float,
                 travel_range_max: float,
                 max_velocity: float,
                 min_velocity: float,
                 min_incremental_motion: float,
                 push_force: float,
                 encoder_resolution: float
                 ) -> None:
        """Initialize actuator.

        Parameters:
            travel_range_min:           Minimum allowed range for actuator in mm.
            travel_range_max:           Maximum allowed range for actuator in mm.
            max_velocity:               Maximum velocity in mm/s.
            min_velocity:               Minimum velocity in mm/s.
            min_incremental_motion:     Minimum incremental motion in mm.
            push_force:                 Maximum push force in N.
            encoder_resolution:         Resolution of encoder in mm
        """
        self.TRAVEL_RANGE = TravelRange(travel_range_min, travel_range_max)
        self.MAX_VELOCITY = max_velocity
        self.MIN_VELOCITY = min_velocity
        self.MIN_INCREMENTAL_MOTION = min_incremental_motion
        self.PUSH_FORCE = push_force
        self.ENCODER_RESOLUTION = encoder_resolution


# max speed set to 0.03mm/s as axials loads over 45N can only support 0.03mm/s
TRA12CC: LinearActuator = LinearActuator(
    0, 12, 0.03, 0.000001, 0.0002, 60, 0.000030517578)
TRB6CC: LinearActuator = LinearActuator(
    0, 6, 0.2, 0.000001, 0.0001, 90, 0.00001447)

CMA25CCL: LinearActuator = LinearActuator(
    0, 25, 0.4, 0.05, 0.0002, 90, 0.000048828)

UTS100PP: LinearActuator = LinearActuator(
    -50, 50, 20, 0.05, 300e-6, 200, 0.0)
