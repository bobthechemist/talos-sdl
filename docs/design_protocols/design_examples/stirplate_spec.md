# Instrument Design: Adafruit 4-Motor Stirplate (stirplate_manager)

## 1. Instrument Overview

*   **Primary Purpose:** To control the speed of up to four DC motors for stirring applications.
*   **Primary Actions:** Set the speed of an individual motor, and stop all motors.
*   **Periodic Telemetry Data:** The current speed setting (as a float from 0.0 to 1.0) for each of the four motors.
*   **Critical Failure Conditions:** The Adafruit Motor FeatherWing is not detected on the I2C bus during initialization.
*   **AI Guidance:** This device controls up to 4 DC motors for stirring. Motor IDs are integers from 1 to 4. Speeds are floats from 0.0 (off) to 1.0 (full speed).

## 2. Hardware Configuration (`STIRPLATE_CONFIG`)

```python
STIRPLATE_CONFIG = {
    "pins": {
        # The Adafruit Motor FeatherWing uses the default I2C pins.
        "SCL": board.SCL,
        "SDA": board.SDA
    },
    "motor_count": 4,
    # Default PWM frequency for the motor driver. 1600 Hz is a common default.
    "pwm_frequency": 1600,
    # AI Guidance 
    "ai_guidance": "This device controls up to 4 DC motors for stirring. Motor IDs are integers from 1 to 4. Speeds are floats from 0.0 (off) to 1.0 (full speed)."
}
```

## 3. Command Interface

| `func` Name | `ai_enabled` | Description | Arguments | Success Condition | Guard Conditions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `set_speed` | `true` | Sets the speed of a single DC motor. | `{"motor_id": int, "speed": float}` | Returns a `SUCCESS` message confirming the new speed. | `motor_id` must be between 1-4. `speed` must be between 0.0 and 1.0. |
| `stop_all` | `true` | Immediately stops all connected motors. | None | Returns a `SUCCESS` message. | None. |

## 4. State Definitions

#### State: `Initialize`
1.  **Purpose:** To connect to the Adafruit Motor FeatherWing via I2C and instantiate the motor objects.
2.  **Entry Actions (`enter()`):**
    *   Attempt to create an `I2C` object for the board.
    *   Attempt to instantiate the `adafruit_motor.MotorKit` object using the I2C bus.
    *   Create a list containing the four motor objects (`kit.motor1`, `kit.motor2`, etc.) and attach it to the `machine` instance (e.g., `machine.motors`).
    *   Set the throttle for all motors to `0.0` to ensure they are off.
3.  **Internal Actions (`update()`):** None. This state transitions immediately.
4.  **Exit Events & Triggers:**
    *   **On Success:** The MotorKit is instantiated without error. Trigger: Transition to `Idle`.
    *   **On Failure:** An exception is raised (e.g., `ValueError` if the board is not found). Trigger: Set an `error_message` flag and transition to `Error`.
5.  **Exit Actions (`exit()`):** None.


