# Guide: Building Your First Instrument Firmware

This comprehensive guide will walk you through the entire process of integrating a new instrument into the Talos-SDL framework. From the initial design phase using the Socratic method, through AI-assisted code generation, to deployment and verification on hardware, you'll learn how to create a complete, functional firmware package that can be controlled and monitored by the host application.

**Our Example Project: The AHT20 Environmental Sensor**

We will build firmware for a microcontroller connected to an Adafruit AHT20 Temperature and Humidity sensor. This is a practical example as it involves:
*   Initializing a specific piece of hardware (the sensor).
*   Periodically reading data (temperature and humidity).
*   Sending this data back to the host as telemetry.
*   Responding to custom commands (e.g., "read the sensor right now").

**Prerequisites:**
*   A PC running Python 3.8+ with the Talos-SDL repository cloned and dependencies installed (`pip install -r requirements.txt`).
*   A CircuitPython-compatible microcontroller (e.g., Raspberry Pi Pico, Adafruit Feather M4) with an AHT20 sensor wired to its I2C pins.
*   The necessary CircuitPython library for the AHT20 sensor. You must copy the `adafruit_ahtx0.mpy` file to the `lib` folder on your microcontroller's `CIRCUITPY` drive.

---

## Part 1: Designing Your Instrument with the Socratic Method

Before writing any code, it's crucial to clearly define your instrument's purpose, capabilities, and behavior. The Talos-SDL framework is built on a state-machine-based design philosophy that prioritizes clarity, modularity, and non-blocking operations.

### Our Design Philosophy

*   **One Machine, One State:** Each instrument is represented by a single, unified `StateMachine` instance. At any given moment, the machine is in one, and only one, well-defined state (e.g., `Initializing`, `Idle`, `Moving`).
*   **Separation of Data and Logic:** We strictly separate the instrument's static configuration (the *data*, like pin numbers and settings) from its dynamic behavior (the *logic*, defined in states and handlers).
*   **Centralized Command Handling:** The `StateMachine` itself is responsible for managing and dispatching commands. States simply indicate *when* the machine should listen for those commands.
*   **Common, Reusable Components:** We leverage a library of common states (`GenericIdle`, `GenericError`) and command handlers (`ping`, `help`) to reduce boilerplate code and ensure consistent behavior across all instruments.

### The Design Process: A Question-Driven Approach

The best way to design a new instrument is to answer a series of questions, moving from a high-level overview down to the specific details of each state. This Socratic, question-driven method ensures all aspects of the instrument's behavior are considered.

#### Step 1: High-Level Instrument Definition

Answer these four core questions about the instrument as a whole:

1.  **What is the primary purpose of this instrument?**
    *   *(AHT20 Example: To measure and report ambient temperature and relative humidity.)*
2.  **What are the primary actions it can perform?**
    *   *(AHT20 Example: Initialize the sensor, periodically read sensor values, and perform a manual read on command.)*
3.  **What data does it need to report back periodically?** (This defines your telemetry.)
    *   *(AHT20 Example: The current temperature (in Celsius) and relative humidity (in %).)*
4.  **What are the critical failure conditions?**
    *   *(AHT20 Example: The AHT20 sensor is not detected on the I2C bus during initialization.)*
5.  **What is the high-level operational guidance for an AI agent?** (This defines your `ai_guidance` in `SUBSYSTEM_CONFIG`).
    *   *(AHT20 Example: This sensor is a simple environmental sensor and does not require pre-positioning by a robotic arm.)*

#### Step 2: Defining the Hardware Configuration (`SUBSYSTEM_CONFIG`)

All static hardware definitions and settings belong in a single `SUBSYSTEM_CONFIG` dictionary in the instrument's `__init__.py` file. This creates a central "dashboard" for the instrument's physical setup.

*   List every pin the microcontroller will use. Give each pin a descriptive name.
*   List any key operational parameters (e.g., default gain, default LED intensity).
*   List any "safe limits" that the instrument must not violate (e.g., min/max intensity).

**Example `SUBSYSTEM_CONFIG` for AHT20:**

```python
AHT20_CONFIG = {
    # The AHT20 uses the board's default I2C pins, so we don't need to define them explicitly.
    # A more complex device would list all pins here (e.g., "SCL": board.SCL, "SDA": board.SDA).
    "ai_guidance": "This sensor is a simple environmental sensor and does not require pre-positioning by a robotic arm.",
}
```

#### Step 3: Defining the Command Interface

This defines the API that the host computer will use to control the instrument. For each custom command, define:

*   **Function Name (`func`):** A short, verb-based name (e.g., `read_now`).
*   **Description:** A clear, one-sentence description of what the command does.
*   **Arguments (`args`):** What data, if any, the host must provide (as a list of dictionaries, e.g., `[{"name": "...", "type": "...", "default": ...}]`).
*   **Success Condition:** What happens when the command completes successfully? (e.g., "Returns a `SUCCESS` message with the sensor data," "Transitions to the `Moving` state.")
*   **Guard Conditions:** What criteria must be met for this command to be accepted? (e.g., "The machine must be homed," "The target coordinates must be within safe limits.")
*   **`ai_enabled` (`Boolean`):** Set to `true` if this command is a high-level, safe, and useful function for an autonomous agent. Set to `false` for low-level debugging commands (e.g., `steps`), or for commands that are superseded by a more abstract one (e.g., `read_all` might be disabled in favor of a more comprehensive `measure` sequence).

**Example Command for AHT20:**

| `func` Name | `ai_enabled` | Description | Arguments | Success Condition | Guard Conditions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `read_now` | `true` | Immediately reads the sensor and returns the values. | `[]` | Returns a `DATA_RESPONSE` message with a payload containing the temperature and humidity. | None. |

#### Step 4: Defining the States

Now, apply the Socratic method to each individual state your instrument will have. Remember, you get `GenericIdle` and `GenericError` (or `GenericErrorWithButton`) for free from `firmware/common/common_states.py`, so you only need to design the states unique to your instrument.

For each custom state, answer these five questions:

1.  **Purpose:** What is this state's single, clear responsibility?
2.  **Entry Actions (`enter()`):** What needs to be set up *the moment* we enter this state? (e.g., start a timer, reset a counter, turn on a pin).
3.  **Internal Actions (`update()`):** What is the main work this state does on *every loop*? (e.g., check a timer, monitor a sensor, step a motor, listen for commands).
4.  **Exit Events & Triggers:** How does this state know its job is finished? What causes a transition to another state? (e.g., a timer expires, a task is complete, an error is detected, an `abort` command is received).
5.  **Exit Actions (`exit()`):** What cleanup is required when leaving this state to ensure the hardware is safe? (e.g., turn off a motor, reset a flag).

**Example State: `Initialize` for AHT20**

1.  **Purpose:** To connect to the AHT20 sensor via the I2C bus.
2.  **Entry Actions (`enter()`):**
    *   Attempt to create an `I2C` object for the board (`i2c = board.I2C()`).
    *   Attempt to instantiate the `adafruit_ahtx0.AHTx0` sensor object using the I2C bus (`machine.sensor = adafruit_ahtx0.AHTx0(i2c)`).
    *   Attach the sensor object to the `machine` instance (`machine.sensor`).
3.  **Internal Actions (`update()`):** None. This state should transition immediately.
4.  **Exit Events & Triggers:**
    *   **On Success:** The sensor is instantiated without error. Trigger: Transition to `Idle`.
    *   **On Failure:** An exception is raised (e.g., `ValueError` if the sensor is not found). Trigger: Set an `error_message` flag and transition to `Error`.
5.  **Exit Actions (`exit()`):** None.

---

## Part 2: AI-Assisted Code Generation

Once your design is documented, you can leverage an AI assistant to generate the initial boilerplate firmware code.

1.  **Open the AI Prompt Template:** Use the contents of `developer_guides/ai_agent_prompt_templates/firmware_generation_template.md` as the system prompt for your AI assistant (e.g., Gemini, ChatGPT).
2.  **Provide Context:** The prompt will ask for two inputs:
    *   **Input 1 (Current Software Stack):** Provide the AI with the code for `shared_lib/` and the firmware for an existing instrument (e.g., `firmware/sidekick/`). This teaches the AI the required architectural patterns.
    *   **Input 2 (New Instrument Design Spec Sheet):** Paste your completed Socratic design document (like the AHT20 example above) into the AI.
3.  **Engage and Clarify:** The AI will ask clarifying questions about your instrument's hardware and desired behavior. Answer these questions to ensure the generated code is accurate.
4.  **Receive Files:** The AI will generate the three initial firmware files: `__init__.py`, `states.py`, and `handlers.py`.

---

## Part 3: Implementing and Deploying the Firmware

Now that you have your design and AI-generated code, it's time to integrate it into the project, deploy it to your microcontroller, and verify its operation.

### Step 1: Create the Firmware Directory

All firmware for a specific instrument lives in its own dedicated folder.

1.  Navigate to the `firmware/` directory in your project.
2.  Create a new folder. For our AHT20 example, we'll name it `aht20_sensor`.
3.  Copy the three generated Python files (`__init__.py`, `states.py`, `handlers.py`) into this new folder.

Your new directory structure will look like this:

```
firmware/
└── aht20_sensor/
    ├── __init__.py
    ├── handlers.py
    └── states.py
```

### Step 2: Configure `boot.py` for the New Device

The `boot.py` file identifies your device to the host computer. Each *type* of device should have a unique Vendor ID (VID) and Product ID (PID).

1.  Open `firmware/common/boot.py`.
2.  Assign a new, unique VID/PID pair. For the AHT20 sensor example, we'll use `101` for both VID and PID for in-lab testing.

```python
# firmware/common/boot.py
# type: ignore
import usb_cdc
import supervisor

# Remember changes to boot.py only go into effect upon power cycling the uC.
# (The reset button won't do it.)

supervisor.set_usb_identification(
    vid=101, # --> New, unique Vendor ID (for AHT20 example)
    pid=101, # --> New, unique Product ID (for AHT20 example)
    product="something awesome",
    manufacturer="Brockport Original Builds")

usb_cdc.enable(console=True, data=True)
```
**Important:** Changes to `boot.py` only take effect after a full power cycle of the microcontroller (unplugging and plugging it back in).

### Step 3: Writing the Firmware Logic (AHT20 Example)

Here are the specific Python files for our AHT20 example. These would typically be generated by your AI assistant based on the design specification you provided.

#### File: `firmware/aht20_sensor/states.py`

```python
# firmware/aht20_sensor/states.py
#type: ignore
import board
from shared_lib.statemachine import State
# The sensor-specific library you copied to the device's lib folder
import adafruit_ahtx0

class Initialize(State):
    """
    Initializes the I2C bus and the AHT20 sensor. This state is custom
    because every instrument has a unique hardware setup.
    """
    @property
    def name(self):
        return 'Initialize'

    def enter(self, machine, context=None):
        super().enter(machine, context)
        try:
            # Create the I2C bus object.
            i2c = board.I2C()  # uses board.SCL and board.SDA
            # Create the sensor object and attach it to the machine instance.
            machine.sensor = adafruit_ahtx0.AHTx0(i2c)
            machine.log.info("AHT20 sensor initialized successfully.")
            # Once initialization is successful, transition to Idle.
            machine.go_to_state('Idle')
        except Exception as e:
            # If the sensor is not found or another error occurs, go to the Error state.
            machine.flags['error_message'] = str(e)
            machine.log.critical(f"Initialization of AHT20 failed: {e}")
            machine.go_to_state('Error')
```

#### File: `firmware/aht20_sensor/handlers.py`

```python
# firmware/aht20_sensor/handlers.py
#type: ignore
from shared_lib.messages import Message, send_problem
from shared_lib.error_handling import try_wrapper # For robust error handling

@try_wrapper # Decorate handler for automatic error message sending
def handle_read_now(machine, payload):
    """
    Handles the device-specific 'read_now' command. This is an example of
    a command that doesn't change state, but returns data directly.
    """
    try:
        temp = machine.sensor.temperature
        humidity = machine.sensor.relative_humidity
        machine.log.info(f"Manual read: Temp={temp:.2f}C, Humidity={humidity:.2f}%")
        
        # Send the data back in a DATA_RESPONSE message payload.
        response = Message.create_message(
            subsystem_name=machine.name,
            status="DATA_RESPONSE",
            payload={
                "metadata": {
                    "data_type": "environmental_reading",
                    "units": {"temperature": "celsius", "humidity": "percent_relative"}
                },
                "data": {
                    "temperature": temp,
                    "humidity": humidity
                }
            }
        )
        machine.postman.send(response.serialize())
    except Exception as e:
        machine.log.error(f"Failed to perform manual read: {e}")
        # The @try_wrapper decorator will automatically call send_problem,
        # so this explicit call is technically redundant if using the decorator.
        # However, it demonstrates how to manually send a problem message.
        send_problem(machine, f"Failed to perform manual read: {e}")
```

#### File: `firmware/aht20_sensor/__init__.py`

```python
# firmware/aht20_sensor/__init__.py
#type: ignore
import board # Required for pin definitions if any
from shared_lib.statemachine import StateMachine
from shared_lib.messages import Message
from communicate.circuitpython_postman import CircuitPythonPostman

# Import resources from our common firmware library
from firmware.common.common_states import GenericIdle, GenericError
from firmware.common.command_library import register_common_commands

# Import the device-specific parts we just wrote
from . import states
from .handlers import handle_read_now

# ============================================================================
# 1. INSTRUMENT CONFIGURATION (Declarative Section)
# ============================================================================
SUBSYSTEM_NAME = "AHT20_SENSOR"
SUBSYSTEM_VERSION = "1.0.0" # Start with a version
SUBSYSTEM_INIT_STATE = "Initialize"

SUBSYSTEM_CONFIG = {
    # No custom pin definitions needed for this simple sensor as it uses default I2C.
    # A more complex device would list all pins here, e.g., "SCL": board.SCL, "SDA": board.SDA.
    "ai_guidance": "This sensor is a simple environmental sensor and does not require pre-positioning by a robotic arm.",
}

# ============================================================================
# 2. ASSEMBLY SECTION
# ============================================================================

# This is our custom telemetry callback function.
# Its purpose is to define WHAT data to send periodically.
def send_aht20_telemetry(machine):
    """Callback function to generate and send the AHT20's telemetry."""
    try:
        temp = machine.sensor.temperature
        humidity = machine.sensor.relative_humidity
        machine.log.debug(f"Telemetry: Temp={temp:.2f}C, Humidity={humidity:.2f}%")
        
        telemetry_message = Message.create_message(
            subsystem_name=machine.name,
            status="TELEMETRY",
            payload={
                "metadata": {
                    "data_type": "environmental_reading",
                    "units": {"temperature": "celsius", "humidity": "percent_relative"}
                },
                "data": {
                    "temperature": temp,
                    "humidity": humidity
                }
            }
        )
        machine.postman.send(telemetry_message.serialize())
    except Exception as e:
        machine.log.error(f"Failed to send AHT20 telemetry: {e}")


# This function builds the instrument-specific status dictionary for the get_info command.
def build_aht20_status(machine):
    """Builds the instrument-specific status dictionary for the get_info command."""
    try:
        temp = machine.sensor.temperature
        humidity = machine.sensor.relative_humidity
        return {
            "sensor_initialized": True,
            "current_temperature_c": round(temp, 2),
            "current_humidity_pct": round(humidity, 2)
        }
    except Exception:
        return {"sensor_initialized": False, "status_error": "Sensor not readable"}


# --- Machine Instantiation ---
machine = StateMachine(
    name=SUBSYSTEM_NAME,
    version=SUBSYSTEM_VERSION,
    config=SUBSYSTEM_CONFIG,
    init_state=SUBSYSTEM_INIT_STATE,
    status_callback=build_aht20_status # Pass the custom status builder
)

# --- Attach Communication Channel (Postman) ---
postman = CircuitPythonPostman(params={"protocol": "serial_cp"})
postman.open_channel()
machine.postman = postman

# --- Add all the states the machine can be in ---
machine.add_state(states.Initialize()) # Our custom state
machine.add_state(GenericIdle(telemetry_callback=send_aht20_telemetry)) # The common idle state
machine.add_state(GenericError()) # The common error state

# --- Define the machine's command interface ---
register_common_commands(machine) # Adds 'ping', 'help', 'set_time', 'get_info'

machine.add_command("read_now", handle_read_now, {
    "description": "Immediately reads the sensor and returns the values.",
    "args": [],
    "ai_enabled": True # Expose this command to the AI agent
})

# --- Add machine-wide flags and settings (Dynamic Runtime Variables) ---
machine.add_flag('error_message', '')
machine.add_flag('telemetry_interval', 10.0) # Send telemetry every 10 seconds
```

### Step 4: The Main Entrypoint (`code.py`)

The `code.py` file is the first thing your microcontroller runs. We need to tell it to import and run our new `aht20_sensor` machine.

1.  Open `firmware/common/code.py`.
2.  Change `SUBSYSTEM` to `aht20_sensor`.

```python
# firmware/common/code.py
#type: ignore
from firmware.aht20_sensor import machine # --> Point to the new machine
from time import sleep

machine.log.setLevel(10) # Set to DEBUG for testing
machine.run()
while True:
    machine.update()
    sleep(0.005)
```

### Step 5: Update the Host Firmware Database

Your host application needs to know how to identify your new device by its VID/PID pair.

1.  Open `host/firmware_db.py`.
2.  Add a new entry for your device using the VID/PID defined in `boot.py`.

```python
# host/firmware_db.py
# ... (existing content) ...

FIRMWARE_DATABASE = {
    808: {
        'manufacturer': 'Brockport Original Builds',
        'products': {
            810: 'Fake Device',
            811: 'Stirplate Manager', 
            812: 'Sidekick',
            813: 'Colorimeter'
        }
    },
    # --- NEW ENTRY FOR AHT20 SENSOR ---
    101: {
        'manufacturer': 'Your Lab Name', # Replace with your lab's name
        'products': {
            101: 'AHT20 Environmental Sensor',
        }
    }
}

# ... (rest of file is the same) ...
```

### Step 6: Install CircuitPython Libraries on Device

Your new instrument firmware will likely depend on specific hardware libraries that are not part of the core Talos-SDL codebase.

1.  **Identify Dependencies:** Check the `import` statements in your new `states.py` file. For the AHT20, this is `import adafruit_ahtx0`.
2.  **Download the Library:** Find the required library on the [CircuitPython Libraries Bundle](https://circuitpython.org/libraries) website.
3.  **Install on Device:** Connect your microcontroller. It will appear as a USB drive named `CIRCUITPY`. Copy the required library file or folder (e.g., `adafruit_ahtx0.mpy`) into the `lib/` directory on the `CIRCUITPY` drive.

### Step 7: Deploy the Firmware

Use the `deploy.py` script to copy the Talos-SDL framework code and your new firmware onto the microcontroller.

1.  **Connect the Device:** Ensure your `CIRCUITPY` drive is visible on your computer. Note its drive letter (e.g., `D:` on Windows) or path.
2.  **Run the Script:** Open a terminal in the project's root directory and run the deployment script, providing the drive and your firmware's folder name.

    ```bash
    # Example for deploying the aht20_sensor to drive D:
    python deploy.py D: aht20_sensor
    ```
3.  **What `deploy.py` Does:** This script will automatically:
    *   Copy the `shared_lib/` and `communicate/` folders to the device.
    *   Copy your specific `firmware/aht20_sensor/` folder.
    *   Customize the `boot.py` file on the device with the correct VID/PID (`101`/`101`).
    *   Customize the `code.py` file to import and run your new `aht20_sensor` `machine`.

### Step 8: Verification with the Control Panel

The final step is to run the host application and verify that it can communicate with your new instrument.

1.  **Launch the Host:** Run the control panel from the project root.
    ```bash
    python host/control_panel.py
    ```
2.  **Check for Success:**
    *   Click **"Scan & Connect All"**.
    *   Your new device, `AHT20 Environmental Sensor`, should appear in the device dropdown list.
    *   Select the device. After a moment, its status panel should update.
    *   Periodic `TELEMETRY` messages from your device should begin appearing in the Raw Message Log, showing temperature and humidity.
    *   The "Available Commands" panel should populate with `ping`, `help`, `set_time`, `get_info`, and your new `read_now` command.
    *   **Test a custom command (`read_now`):**
        *   Double-click `read_now` in the "Available Commands" tree to populate the command entries.
        *   The arguments field should be empty, as `read_now` takes no arguments.
        *   Click **"Send"**.
        *   You should see a green `RECV_DATA_RESPONSE` message in the log containing the current temperature and humidity, confirming the command was executed successfully.
    *   **Test a common command (`get_info`):**
        *   Double-click `get_info`.
        *   Click **"Send"**.
        *   You should receive a `RECV_DATA_RESPONSE` with detailed status information, including `sensor_initialized`, `current_temperature_c`, and `current_humidity_pct` from your `build_aht20_status` callback.

---

Congratulations! You have successfully designed, generated, deployed, and tested a new instrument for the Talos-SDL ecosystem. You can now follow this pattern to integrate any new hardware into the system.

