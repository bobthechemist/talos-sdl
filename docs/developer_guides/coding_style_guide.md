

# Automated Labroatory Instrument Framework ALIF Framework Style Guide

*aka: the sdl sandbox*

### 1. Unified Architecture (Host-Device MVC)
The system follows a strict **Model-View-Controller (MVC)** pattern on the Host and a **Finite State Machine (FSM)** pattern on the Device.
*   **Host Model:** `Device` objects act as "Digital Twins" of hardware.
*   **Host Controller:** The `DeviceManager` is the sole orchestrator. No script or UI may instantiate a private `Postman` or serial connection; all must route through the `DeviceManager`.
*   **Device:** Microcontrollers must run CircuitPython and adhere to the state-machine-driven firmware structure.

### 2. Standard Firmware Directory Structure
Every instrument firmware must be a self-contained module in the `firmware/` directory with three mandatory files:
1.  **`__init__.py`**: Assembly and configuration (Declarative Section + Assembly Section).
2.  **`states.py`**: Behavior logic (State classes).
3.  **`handlers.py`**: Interface logic (Command functions).

### 3. Finite State Machine (FSM) Logic
Instruments must be in exactly one state at a time. 
*   **States as Classes:** Every state inherits from `State` and implements `enter()`, `update()`, and `exit()`.
*   **Non-Blocking update:** The `update()` method must be non-blocking. Use `time.monotonic()` comparisons instead of `time.sleep()` for timed events to ensure the machine remains responsive to `listen_for_instructions()`.
*   **Initialization:** Every machine must start in an `Initialize` state before transitioning to `Idle`.

### 4. Standardized JSON Messaging
All communication is human-readable JSON. A message must contain:
*   `subsystem_name`: Uppercase string (e.g., `"SIDEKICK"`).
*   `status`: Must be one of: `INSTRUCTION`, `SUCCESS`, `PROBLEM`, `DATA_RESPONSE`, `TELEMETRY`, `INFO`, `WARNING`, `DEBUG`.
*   `payload`: A dictionary. For `INSTRUCTION`, it must use a `func` string and an `args` **dictionary** (never a list).

### 5. Naming Conventions
*   **Subsystem Names:** All caps (e.g., `STIRPLATE`, `COLORIMETER`).
*   **State Classes:** PascalCase, typically ending in the action or role (e.g., `Blinking`, `GenericIdle`).
*   **Command Handlers:** `snake_case` prefixed with `handle_` (e.g., `handle_move_to`).
*   **Variables/Functions:** Standard `snake_case`.
*   **Hardware Config:** Uppercase (e.g., `SUBSYSTEM_CONFIG`).

### 6. Separation of Data and Logic
Strictly separate static configuration from dynamic runtime state:
*   **`SUBSYSTEM_CONFIG`**: Stored in `__init__.py`. Contains immutable hardware data (pins, physical constants, safe limits).
*   **`machine.flags`**: Dictionary for mutable runtime data (e.g., `is_homed`, `current_m1_steps`).
*   **Calculated Status:** Use a `status_callback` (e.g., `build_status`) to generate real-time reports rather than storing redundant data.

### 7. The Postman & Secretary Pattern
Communication is abstracted through the `Postman` class. 
*   The **Postman** handles low-level transport (Serial, CircuitPython CDC, or Dummy).
*   The **Secretary** (on the device) or **DeviceManager** (on the host) handles the routing, filing, and reading of messages into buffers.

### 8. Command Handlers & Guard Conditions
Handlers in `handlers.py` serve as the API. 
*   **Non-Blocking:** Handlers must return immediately. If a command takes time (like `move`), the handler sets target flags and changes the machine state.
*   **Guards:** Handlers must validate prerequisites (e.g., `check_homed`) and argument ranges before execution.
*   **Decorators:** Use the `try_wrapper` to catch exceptions and automatically send `PROBLEM` messages back to the host.

### 9. State Sequencer Pattern
For complex, multi-step workflows (e.g., "LED on -> Read -> LED off"), use the `StateSequencer`.
*   **Sequence Definitions:** Defined as a list of dictionaries: `{"state": "StateName", "label": "Description"}`.
*   **Context:** Use the `sequencer.context` dictionary to pass data between states in a sequence (e.g., passing a sensor reading from `ReadSensor` to `TurnOffLED`).

### 10. AI-Ready Protocol
To support Autonomous Agent control (AI Planner):
*   **Metadata:** Commands must include a `description`, `args` (with types and defaults), and `ai_enabled` boolean.
*   **Explicitness:** Use `effects` and `usage_notes` in command definitions to provide the AI with the consequences of an action.
*   **Discovery:** The host must use the `help` command to dynamically build the AI's understanding of the instrument's capabilities.