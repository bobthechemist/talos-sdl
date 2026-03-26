# **Talos-SDL:** Firmware Design Protocol (Version 1.0)

This protocol establishes the _Standard Instrument Blueprint_ - a standard way to develop firmware for all instruments within the Self-Driven Laboratory framework. Adherence to this protocol is mandatory to ensure that all firmware is consistent, robust, maintainable, and interoperable with the host application.

## Guiding Principles

*   **Modularity:** Each instrument's firmware is a self-contained module.
*   **Separation of Concerns:** A strict separation is maintained between configuration (data), state logic (behavior), and command handling (interface).
*   **Declarative Assembly:** Instruments are assembled using a clear, declarative pattern, minimizing boilerplate code and reducing errors.
*   **Non-Blocking Logic:** Firmware must remain responsive at all times. Long-running operations must be handled by states, not by blocking code within command handlers.

## File Structure

All firmware for a specific instrument MUST reside in its own directory (e.g., `firmware/sidekick/`). This directory MUST contain the following three Python files:

*   `__init__.py`: The master assembly file. Contains all static configuration and the instantiation of the `StateMachine`.
*   `states.py`: Contains all custom `State` classes that define the instrument's unique runtime behaviors.
*   `handlers.py`: Contains all handler functions that execute the logic for custom commands received from the host.

---

### `__init__.py`: Configuration and Assembly

**Guiding Principle:** The `__init__.py` file follows a **Declarative Assembly** pattern. Its primary role is to define *what* the instrument is through a set of standardized variables and then assemble the `StateMachine` instance from those declarations.

#### Structure

The file is divided into two main parts:

1.  **The Declarative Section:** A set of top-level variables that a developer configures.
2.  **The Assembly Section:** Standardized, boilerplate code that builds the machine from the declarations.

#### Part 1: The Declarative Section

This section MUST be at the top of the file. It defines the instrument's identity and static configuration.

1.  **Top-Level Imports:** Any modules required by the configuration dictionary (most commonly `import board`) MUST be placed at the very top of the file.

2.  **Identity Variables:** The following three variables MUST be defined:
    *   `SUBSYSTEM_NAME` (String): The unique, uppercase name for this instrument (e.g., `"SIDEKICK"`).
    *   `SUBSYSTEM_VERSION` (String): The semantic version of the firmware (e.g., `"1.1.0"` for Major.Minor.Patch).
    *   `SUBSYSTEM_INIT_STATE` (String): The name of the first state the machine should enter (almost always `"Initialize"`).

3.  **Configuration Dictionary:**
    *   A dictionary named `SUBSYSTEM_CONFIG` MUST be defined.
    *   This dictionary MUST contain all static, boot-time parameters, such as pin definitions, physical constants, motor settings, and safe operational limits. It is the single source of truth for the instrument's hardware data.

**Example Declarative Section:**
```python
# firmware/sidekick/__init__.py

import board

# ============================================================================
# 1. DECLARATIVE SECTION
# ============================================================================
SUBSYSTEM_NAME = "SIDEKICK"
SUBSYSTEM_VERSION = "1.1.0"
SUBSYSTEM_INIT_STATE = "Initialize"

SUBSYSTEM_CONFIG = {
    "pins": {
        "motor1_step": board.GP1, 
        "user_button": board.GP20,
        # ... all other pin definitions
    },
    "motor_settings": {
        "max_speed_sps": 200,
        # ... all other motor settings
    }
    # ... etc.
}
```

#### Part 2: The Assembly Section

This section is largely standardized across all instruments.

1.  **Callback Functions:**
    *   **Telemetry:** A `send_telemetry(machine)` function SHOULD be defined to generate and send the instrument's periodic `TELEMETRY` message. This function is passed to the `GenericIdle` state.
    *   **Status Info:** A `build_status(machine)` function MUST be defined. This function implements the "Computed Status" pattern. Its only job is to return a dictionary containing the public-facing status information (e.g., `{'homed': machine.flags.get('is_homed')}`). This function is passed to the `StateMachine` constructor.

2.  **Machine Instantiation:**
    *   The `StateMachine` instance MUST be created by passing the declarative variables and the `build_status` callback to its constructor.

    ```python
    machine = StateMachine(
        name=SUBSYSTEM_NAME,
        version=SUBSYSTEM_VERSION,
        config=SUBSYSTEM_CONFIG,
        init_state=SUBSYSTEM_INIT_STATE,
        status_callback=build_status
    )
    ```

3.  **Component Attachment:** The `Postman` communication channel is attached to the `machine`.

4.  **Adding States, Commands, and Flags:**
    *   All required states (both custom from `states.py` and common from `common_states.py`) are added using `machine.add_state()`.
    *   Common commands are registered with `register_common_commands(machine)`.
    *   All custom commands are added using `machine.add_command()`.
    *   All required internal, dynamic flags are initialized using `machine.add_flag()`. This includes the internal flags that the `build_status` function relies on (e.g., `machine.add_flag('is_homed', False)`).

---

### `states.py`: Runtime Behavior

**(TODO: This section will be expanded with detailed protocols for state design.)**

**Guiding Principle:** States encapsulate **behavior and logic**. They are responsible for managing long-running, non-blocking operations and updating the machine's internal flags to reflect its current condition.

---

### `handlers.py`: Command Interface

**(TODO: This section will be expanded with detailed protocols for handler design.)**

TODO: Consider adding "returns": {"data_type", "units", "schema"} to the handler definition.

**Guiding Principle:** Handlers are the **entry point** for external commands. They MUST be non-blocking. Their primary role is to validate incoming arguments, set flags for the state machine to act upon, and trigger state transitions.