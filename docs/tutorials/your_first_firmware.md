## Guide: Creating New Firmware for a Self-Driven Laboratory Instrument

### 1. Introduction

This guide will walk you through the process of creating firmware for a new instrument to integrate into the self-driven laboratory framework. Our goal is to create a complete, functional firmware package that can be controlled and monitored by the host application.

**Our Example Project: The AHT20 Environmental Sensor**

We will build firmware for a microcontroller connected to an Adafruit AHT20 Temperature and Humidity sensor. This is a great example as it involves:
*   Initializing a specific piece of hardware (the sensor).
*   Periodically reading data (temperature and humidity).
*   Sending this data back to the host as telemetry.
*   Responding to custom commands (e.g., "read the sensor right now").

**Prerequisites:**
*   A CircuitPython-compatible microcontroller.
*   An AHT20 sensor wired to the microcontroller's I2C pins.
*   The project code for the self-driven laboratory framework.
*   The necessary CircuitPython library for the AHT20 sensor. You must copy the `adafruit_ahtx0.mpy` file to the `lib` folder on your microcontroller's `CIRCUITPY` drive.

### 2. Step 1: Create the Firmware Directory

All firmware for a specific instrument lives in its own dedicated folder.

1.  Navigate to the `firmware/` directory in your project.
2.  Create a new folder. For our example, we'll name it `aht20_sensor`.
3.  Inside `aht20_sensor/`, create three empty Python files:
    *   `__init__.py`: This will be the master "assembly" file for the machine.
    *   `states.py`: This will define the unique behaviors of our sensor.
    *   `handlers.py`: This will define the logic for custom commands.

Your new directory structure will look like this:
```
firmware/
└── aht20_sensor/
    ├── __init__.py
    ├── handlers.py
    └── states.py
```

### 3. Step 2: Configure `boot.py` for the New Device

The `boot.py` file identifies your device to the host computer. Each *type* of device should have a unique Vendor ID (VID) and Product ID (PID).

1.  Open `firmware/common/boot.py`.
2.  Assign a new, unique VID/PID pair. Let's use `101` for our sensor PID and VID
3.  We haven't come up with a standard for VIDs and PIDs yet, VID 808 is reserved for Brockport Original Builds and 101 is reserved for in-lab testing. 

```python
# firmware/common/boot.py
supervisor.set_usb_identification(
    vid=101, # --> New, unique Vendor ID
    pid=101, # --> New, unique Product ID
)

usb_cdc.enable(console=True, data=True)
```
**Important:** Changes to `boot.py` only take effect after a full power cycle of the microcontroller (unplugging and plugging it back in).

### 4. Step 3: Writing the Firmware Logic

Now we will write the code for the three files we created.

#### The `states.py` File: Defining Unique Behaviors

This file contains `State` classes that are unique to this instrument. For most devices, the only required custom state is `Initialize`, as every piece of hardware has a different setup procedure.

*   **What you get from `common`:** `GenericIdle` and `GenericError`. You do not need to write these.
*   **What you must write:** `Initialize` and any other custom active states (like `Blinking` for the fake device).

**File: `firmware/aht20_sensor/states.py`**
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

    def enter(self, machine):
        super().enter(machine)
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

#### The `handlers.py` File: Defining Custom Commands

This file contains the functions that execute your device's custom commands.

*   **What you get from `common`:** Handlers for `ping` and `help`. You do not need to write these.
*   **What you must write:** A handler function for every custom command your device supports.

Let's create a `read_now` command that immediately takes a sensor reading and sends it back.

**File: `firmware/aht20_sensor/handlers.py`**
```python
# firmware/aht20_sensor/handlers.py
#type: ignore
from shared_lib.messages import Message

def handle_read_now(machine, payload):
    """
    Handles the device-specific 'read_now' command. This is an example of
    a command that doesn't change state, but returns data directly.
    """
    try:
        temp = machine.sensor.temperature
        humidity = machine.sensor.relative_humidity
        machine.log.info(f"Manual read: Temp={temp:.2f}C, Humidity={humidity:.2f}%")
        
        # Send the data back in a SUCCESS message payload.
        response = Message.create_message(
            subsystem_name=machine.name,
            status="SUCCESS",
            payload={
                "temperature": temp,
                "humidity": humidity
            }
        )
        machine.postman.send(response.serialize())
    except Exception as e:
        machine.log.error(f"Failed to perform manual read: {e}")
        response = Message.create_message(
            subsystem_name=machine.name,
            status="PROBLEM",
            payload={"error": str(e)}
        )
        machine.postman.send(response.serialize())
```

#### The `__init__.py` File: Assembling the Machine

This is the blueprint for your machine. It imports all the pieces (states, handlers, libraries) and assembles them into the final `machine` object.

**File: `firmware/aht20_sensor/__init__.py`**
```python
# firmware/aht20_sensor/__init__.py
#type: ignore
from shared_lib.statemachine import StateMachine
from shared_lib.messages import Message
from communicate.circuitpython_postman import CircuitPythonPostman

# Import resources from our common firmware library
from firmware.common.common_states import GenericIdle, GenericError
from firmware.common.command_library import register_common_commands

# Import the device-specific parts we just wrote
from . import states
from .handlers import handle_read_now

# This is our custom telemetry callback function.
# Its purpose is to define WHAT data to send periodically.
def send_aht20_telemetry(machine):
    """Callback function to generate and send the AHT20's telemetry."""
    temp = machine.sensor.temperature
    humidity = machine.sensor.relative_humidity
    machine.log.debug(f"Telemetry: Temp={temp:.2f}C, Humidity={humidity:.2f}%")
    
    telemetry_message = Message.create_message(
        subsystem_name=machine.name,
        status="TELEMETRY",
        payload={
            "temperature": temp,
            "humidity": humidity
        }
    )
    machine.postman.send(telemetry_message.serialize())

# 1. Create the state machine instance
machine = StateMachine(init_state='Initialize', name='AHT20_SENSOR')

# 2. Attach the communication channel (Postman)
postman = CircuitPythonPostman(params={"protocol": "serial_cp"})
postman.open_channel()
machine.postman = postman

# 3. Add all the states the machine can be in
machine.add_state(states.Initialize()) # Our custom state
machine.add_state(GenericIdle(telemetry_callback=send_aht20_telemetry)) # The common idle state
machine.add_state(GenericError()) # The common error state

# 4. Define the machine's command interface
register_common_commands(machine) # Adds 'ping' and 'help'
machine.add_command("read_now", handle_read_now, {
    "description": "Immediately reads the sensor and returns the values.",
    "args": []
})

# 5. Add machine-wide flags and settings
machine.add_flag('error_message', '')
machine.add_flag('telemetry_interval', 10.0) # Send telemetry every 10 seconds
```

### 5. Step 4: The Main Entrypoint (`code.py`)

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

### 6. Step 5: Updating the Host Application

Your firmware is now complete, but the host interface doesn't know what VID/PID `809` means. We need to add an entry to our database.

1.  Open `host_app/firmware_db.py`.
2.  Add a new entry for your device.

```python
# host_app/firmware_db.py

FIRMWARE_DATABASE = {
    808: {
        'manufacturer': 'Brockport Original Builds',
        'products': {
            808: 'Fake Device',
        }
    },
    # --- NEW ENTRY ---
    101: {
        'manufacturer': 'Your lab name here',
        'products': {
            101: 'AHT20 Environmental Sensor',
        }
    }
}
# ... (rest of file is the same) ...
```

### 7. Step 6: Deployment and Debugging

You are now ready to deploy and test your new instrument.

1.  **Deploy:** Run your `deploy_firmware.bat` script, providing the correct drive letter for your microcontroller. This will copy `firmware/` and `shared_lib/` to the device.
    ```bash
    deploy_firmware.bat G
    ```
2.  **Run Host Interface:** From your project root directory, run the host GUI.
    ```bash
    python -m host_app.gui.host_interface
    ```
3.  **Test:**
    *   Click **"Scan for Devices"**. You should see your new device appear in the dropdown: `AHT20 Environmental Sensor - COMx (VID:101, PID:101)`.
    *   Click **"Connect"**.
    *   **Observe Telemetry:** Every 10 seconds, you should see a `TELEMETRY` message appear in the log with the current temperature and humidity.
    *   **Test Common Commands:**
        *   Send a `{"func": "ping"}` command and verify you get a `pong` response.
        *   Click **"Get Commands"** (which sends `{"func": "help"}`) and verify the response lists `ping`, `help`, and your new `read_now` command.
    *   **Test Custom Command:**
        *   Enter `{"func": "read_now"}` into the payload box and click **"Send Instruction"**.
        *   You should immediately receive a `SUCCESS` message containing the sensor data.
    *   **Test Error in Command:**
        *   Enter `{"func": "foobar"}` into the payload box and click **"Send Instruction"**.
        *   You should immediately receive a `PROBLEM` message indicating that the function is unknown.

Congratulations! You have successfully created, deployed, and tested a new instrument for your self-driven laboratory. You can now follow this pattern to integrate any new hardware into the system. 