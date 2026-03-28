# Instrument Design: [Instrument Name] ([slug_name])

## 1. Instrument Overview

*   **Primary Purpose:** [e.g., To measure ambient light and control an indicator LED.]
*   **Primary Actions:** [e.g., Read sensor, set LED brightness, blink.]
*   **Periodic Telemetry Data:** [Define what the device reports every few seconds, e.g., current sensor value.]
*   **Critical Failure Conditions:** [e.g., I2C sensor not found, motor stall detected.]
*   **AI Guidance:** [High-level instruction for the LLM, e.g., "Use this device to signal status. Do not exceed brightness level 5 during night cycles."]

## 2. Hardware Configuration (`CONFIG` dictionary)

```python
[SLUG]_CONFIG = {
    "pins": {
        # List every physical pin used
        "SCL": board.SCL,
        "SDA": board.SDA,
        "indicator_led": board.GP2,
    },
    # Operational parameters
    "default_setting": 10,
    "max_safe_value": 100,
    
    # AI Guidance (included in metadata for the agent)
    "ai_guidance": "...",
}
```

## 3. Command Interface

| `func` Name | `ai_enabled` | Description | Arguments | Success Condition | Guard Conditions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `read_now` | `true` | Reads the sensor immediately. | `[]` | Returns `DATA_RESPONSE` with value. | None. |
| `set_led` | `true` | Sets LED brightness. | `[{"name": "level", "type": "int"}]` | Returns `SUCCESS`. | Level must be 0-255. |

## 4. State Definitions

#### State: `Initialize`
1.  **Purpose:** [e.g., Establish I2C communication and set pins to safe defaults.]
2.  **Entry Actions (`enter()`):**
    *   [e.g., Instantiate I2C bus.]
    *   [e.g., Setup digital IO pins.]
3.  **Internal Actions (`update()`):** None. (Immediate transition)
4.  **Exit Events & Triggers:**
    *   **On Success:** Trigger: Transition to `Idle`.
    *   **On Failure:** Trigger: Set `error_message` and transition to `Error`.
5.  **Exit Actions (`exit()`):** None.

#### State: `[CustomStateName]`
1.  **Purpose:** [What is the specific job of this state?]
2.  **Entry Actions (`enter()`):** [e.g., Start a timer, turn on a motor.]
3.  **Internal Actions (`update()`):** [e.g., Check if goal reached, monitor safety.]
4.  **Exit Events & Triggers:** [e.g., Task complete, timeout, or abort command.]
5.  **Exit Actions (`exit()`):** [e.g., Stop motor, reset flags.]