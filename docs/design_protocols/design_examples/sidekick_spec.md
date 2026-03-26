# Instrument design: Sidekick liquid dispenser (sidekick)

## 1. Instrument Overview (Unchanged)
*   **Primary purpose:** To dispense liquid from four displacement pumps with 2-dimensional resolution.
*   **Primary actions:** Move dispensing effector, dispense liquids.
*   **Periodic telemetry data:** Current end effector position in Cartesian `(x, y)` coordinates.
*   **Critical failure conditions:** Endstops triggered unexpectedly during a move.

## 2. Hardware Configuration (`SIDEKICK_CONFIG`)


``` python
SIDEKICK_CONFIG = {
    "pins": {
        # --- Motor 1 (Top Motor) ---
        "motor1_step": board.GP1,
        "motor1_dir": board.GP0,
        "motor1_enable": board.GP7,  # Was 'motor1_sleep'

        # --- Motor 2 (Bottom Motor) ---
        "motor2_step": board.GP10,
        "motor2_dir": board.GP9,
        "motor2_enable": board.GP16, # Was 'motor2_sleep'
        
        # NOTE: Microstepping pins are recorded here for completeness.
        # Simple drivers use these, but advanced drivers (TMC) use UART/SPI.
        # This framework can be extended later to use them if needed.
        "motor1_m0": board.GP6,
        "motor1_m1": board.GP5,
        "motor2_m0": board.GP15,
        "motor2_m1": board.GP14,

        # --- Endstops ---
        # The old code referred to them by location ('front'/'rear').
        # Tying them to the motor they home is more robust.
        "endstop_m1": board.GP18, # Was 'lsfront'
        "endstop_m2": board.GP19, # Was 'lsrear'

        # --- User Button ---
        "user_button": board.GP20, # Was 'purgebutton'

        # --- Pumps ---
        "pump1": board.GP27,
        "pump2": board.GP26,
        "pump3": board.GP22,
        "pump4": board.GP21,
    },
    
    "motor_settings": {
        # Your code mentions both 1.8 and 0.9 degree motors, but the
        # stepsize calculation (0.1125) points to 1/8 microstepping
        # on a 0.9 degree motor. (0.9 degrees / 8 microsteps).
        "step_angle_degrees": 0.9,
        "microsteps": 8,
        # Calculated from stepdelay = 0.0010. A full step cycle is two delays.
        # 1 / (2 * 0.0010) = 500 steps per second.
        "max_speed_sps": 500,
    },

    "pump_timings": {
        # Extracted from the dispense() function's time.sleep() calls.
        "aspirate_time": 0.1, # seconds
        "dispense_time": 0.1, # seconds
    },

    "kinematics": {
        # These are the physical dimensions of the SCARA arm segments.
        # They come from the __init__ arguments: L1, L2, L3, Ln
        "L1": 7.0,
        "L2": 3.0,
        "L3": 10.0,
        "Ln": 0.5,
    },

    "safe_limits": {
        # These will need to be determined experimentally after homing,
        # but we can create placeholders. These are in logical motor steps.
        "m1_min_steps": 0,
        "m1_max_steps": 10000, # Example value
        "m2_min_steps": 0,
        "m2_max_steps": 10000, # Example value
    },
    # --- NEW: Added based on your feedback ---
    "home_position": {
        # A safe "parking" spot in Cartesian (x, y) coordinates.
        # If set to None, the home command will use the motor-zero position.
        "x": 10.0, # cm
        "y": 5.0   # cm
    },
    "pump_offsets": {
        # The (dx, dy) offset in cm from the arm's center point for each pump.
        "p1": {"dx": 0.5, "dy": 0.0},
        "p2": {"dx": 0.0, "dy": 0.5},
        "p3": {"dx": -0.5, "dy": 0.0},
        "p4": {"dx": 0.0, "dy": -0.5},
    }
}
```

## 3. Command Interface 

| `func` Name | Description | Arguments | Success Condition | Guard Conditions |
| :--- | :--- | :--- | :--- | :--- |
| `home` | Finds the zero position using endstops, then moves to the pre-defined safe parking spot. | None | Returns a `SUCCESS` message when complete. | None. |
| `move_to` | Moves the arm's center point to an **absolute** `(x, y)` Cartesian coordinate. | `{"x": float, "y": float}` | Returns a `SUCCESS` message with the final position. | Must be homed. Coordinates must be within safe travel limits. |
| `move_rel` | Moves the arm relative to its **current** position by `(dx, dy)`. | `{"dx": float, "dy": float}` | Returns a `SUCCESS` message with the final position. | Must be homed. Target coordinates must be within safe travel limits. |
| `dispense` | Dispenses from a specified pump **at the current location**. Involves a small offset move for the pump. | `{"pump": str, "vol": float}` | Returns a `SUCCESS` message. | Must be homed. `pump` must be valid. `vol` will be rounded down and a warning issued. |
| `dispense_at` | An **atomic operation** that moves the specified pump to an absolute `(x, y)` coordinate and then dispenses. | `{"pump": str, "vol": float, "x": float, "y": float}` | Returns a `SUCCESS` message. | Must be homed. All parameters must be valid. Target coordinates must be safe. |

*(Note: The `calibrate` command is no longer needed, as its functions are handled by the `Homing` state and the new `CONFIG` entries.)*

## 4. State Definitions 

*   **`Initialize`:**
    *   **Purpose:** To configure all hardware objects based on `machine.config`.
    *   **Exit Events:** On success, transitions to `Homing`. On failure, transitions to `Error`.
    *   **Exit Actions:** On failure, ensure motors are disabled.

*   **`Homing`:**
    *   **Purpose:** To establish the arm's absolute zero position and determine the maximum travel limits.
    *   **Entry Actions:** Begins moving Motor 1 towards its endstop.
    *   **Internal Actions:**
        1.  When Motor 1 endstop is hit, set its logical position to `0`. Begin moving Motor 1 in the opposite direction to find the maximum travel distance.
        2.  Repeat the process for Motor 2.
        3.  Store the discovered travel limits in `machine.flags`.
    *   **Exit Events:**
        *   **Success:** Both motors are homed and limits are found. Set `is_homed = True` and trigger transition to `Idle`.
        *   **Failure:** An endstop is not found within a maximum number of steps (timeout). Trigger transition to `Error`.

*   **`Moving`:** (The "Motion Engine")
    *   **Purpose:** To execute a planned move from a start point to a target point. It is a generic state that does not know the reason for the move.
    *   **Entry Actions:** Reads `target_x/y` from flags, calculates the motor trajectory (steps, directions).
    *   **Internal Actions:** Pulses stepper motors according to the trajectory. Continuously checks for unexpected endstop triggers.
    *   **Exit Events:**
        *   **Success:** Target coordinates are reached. **It then checks the `machine.flags['on_move_complete']` flag.**
            *   If the flag is `'Dispensing'`, it transitions to the `Dispensing` state.
            *   Otherwise, it transitions to the default `Idle` state.
        *   **Failure:** An unexpected endstop is triggered. Set `is_homed = False` and trigger transition to `Error`.
    *   **Exit Actions:** Clear the `on_move_complete` flag to ensure it doesn't affect the next move.

*   **`Dispensing`:**
    *   **Purpose:** To execute the timed pulse sequence for one or more pumps. **This state does not perform any arm movement.**
    *   **Entry Actions:** Reads dispense parameters (`pump`, `cycles`) from flags. Initializes timers for the pump sequence.
    *   **Internal Actions:** Runs the non-blocking aspirate/dispense timing loop for all active pumps.
    *   **Exit Events:**
        *   **Success:** All requested dispense cycles are complete. Trigger transition to `Idle`.
    *   **Exit Actions:** Sends a `SUCCESS` message to the host.


