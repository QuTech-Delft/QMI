class LinearActuator:
    """Linear actuator."""

    def __init__(self,
                 travel_range: float,
                 max_velocity: float,
                 min_velocity: float,
                 min_incremental_motion: float,
                 push_force: float,
                 encoder_resolution: float
                 ) -> None:
        """Initialize actuator.

        Parameters:
            travel_range:               Maximum allowed range for actuator in mm.
            max_velocity:               Maximum velocity in mm/s.
            min_velocity:               Minimum velocity in mm/s.
            min_incremental_motion:     Minimum incremental motion in mm.
            push_force:                 Maximum push force in N.
            encoder_resolution:         Resolution of encoder in mm
        """
        self.TRAVEL_RANGE = travel_range
        self.MAX_VELOCITY = max_velocity
        self.MIN_VELOCITY = min_velocity
        self.MIN_INCREMENTAL_MOTION = min_incremental_motion
        self.PUSH_FORCE = push_force
        self.ENCODER_RESOLUTION = encoder_resolution


# max speed set to 0.03mm/s as axials loads over 45N can only support 0.03mm/s
TRA12CC: LinearActuator = LinearActuator(
    12, 0.03, 0.000001, 0.0002, 60, 0.000030517578)
TRB6CC: LinearActuator = LinearActuator(
    6, 0.2, 0.000001, 0.0001, 90, 0.00001447)

CMA25CCL: LinearActuator = LinearActuator(
    25, 0.4, 0.05, 0.0002, 90, 0.000048828)
