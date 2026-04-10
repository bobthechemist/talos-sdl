# firmware/colorimeter/handlers.py
# REFACTORED: This file updates all message payloads to comply with messaging.md
# and introduces a 'measure' command to demonstrate the StateSequencer.
# type: ignore
from shared_lib.messages import Message, send_problem, send_success
from shared_lib.error_handling import try_wrapper

# This dictionary maps the user-friendly channel names to the actual
# attribute names on the adafruit_as7341 sensor object.
CHANNEL_NAMES = [
    "violet", "indigo", "blue", "cyan", "green",
    "yellow", "orange", "red", "clear", "nir"
]

# The list of valid gain values, as defined by the sensor's library.
# The AS7341 library uses a gain index from 0-10, which corresponds to these values.
VALID_GAINS = [0.5, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512]

# ============================================================================
# COMMAND HANDLERS (REFACTORED)
# ============================================================================

@try_wrapper
def handle_read_all(machine, payload):
    """
    Handles the 'read_all' command.
    REFACTORED: Returns a DATA_RESPONSE with a structured payload.
    """
    readings_tuple = machine.sensor.all_channels
    
    # Create a more descriptive dictionary for the data payload
    readings_dict = dict(zip(CHANNEL_NAMES, readings_tuple))
    machine.log.info(f"Read all channels: {readings_dict}")
    
    response = Message.create_message(
        subsystem_name=machine.name,
        status="DATA_RESPONSE",
        payload={
            "metadata": {
                "data_type": "color_spectrum",
                "units": "counts"
            },
            "data": readings_dict
        }
    )
    machine.postman.send(response.serialize())

@try_wrapper
def handle_get_settings(machine, payload):
    """
    Handles the 'get_settings' command.
    REFACTORED: Returns a DATA_RESPONSE with a structured payload.
    """
    settings_data = {
        "gain": machine.sensor.gain,
        "led_is_on": machine.sensor.led,
        "intensity_ma": machine.sensor.led_current
    }
    
    response = Message.create_message(
        subsystem_name=machine.name,
        status="DATA_RESPONSE",
        payload={
            "metadata": { "data_type": "sensor_settings" },
            "data": settings_data
        }
    )
    machine.postman.send(response.serialize())
 
@try_wrapper
def handle_set_settings(machine, payload):
    """
    Handles the 'set_settings' command. Can set multiple parameters at once.
    BUG FIX: Correctly sets 'led_current' instead of 'intensity'.
    """
    args = payload.get("args", {})
    if not isinstance(args, dict) or not args:
        send_problem(machine, "Invalid or empty 'args' object provided.")
        return

    # Keep track of which parameters were successfully set
    settings_applied = []

    if "gain" in args:
        new_gain = args["gain"]
        if new_gain in VALID_GAINS:
            # The library uses an index for gain, so we find it.
            machine.sensor.gain = VALID_GAINS.index(new_gain)
            settings_applied.append(f"gain={new_gain}x")
        else:
            send_problem(machine, f"Invalid gain value {new_gain}. Valid gains are: {VALID_GAINS}.")
            return # Stop processing on invalid input

    if "led" in args:
        led_state = args["led"]
        if isinstance(led_state, bool):
            machine.sensor.led = led_state
            settings_applied.append(f"led={'ON' if led_state else 'OFF'}")
        else:
            send_problem(machine, "Invalid 'led' value; must be a boolean (true/false).")
            return

    if "intensity" in args:
        intensity = args["intensity"]
        min_i = machine.config["min_intensity"]
        max_i = machine.config["max_intensity"]
        if isinstance(intensity, int) and min_i <= intensity <= max_i:
            # BUG FIX: The attribute is `led_current`, not `intensity`.
            machine.sensor.led_current = intensity
            settings_applied.append(f"intensity={intensity}mA")
        else:
            send_problem(machine, f"Invalid 'intensity'; must be an integer between {min_i} and {max_i}.")
            return

    if settings_applied:
        send_success(machine, f"Settings applied: {', '.join(settings_applied)}.")
    else:
        send_problem(machine, f"No valid parameters found in request: {args}")

# ============================================================================
# NEW COMMAND HANDLER FOR STATE SEQUENCER
# ============================================================================
def handle_measure(machine, payload):
    """
    Initiates a non-blocking, multi-step measurement sequence.
    This demonstrates the use of the StateSequencer for complex tasks.
    """
    # Define the sequence of states and their labels.
    sequence = [
        {"state": "TurnOnLED", "label": "Powering illuminator"},
        {"state": "ReadSensor", "label": "Acquiring data"},
        {"state": "TurnOffLED", "label": "Finalizing and reporting"}
    ]
    
    machine.log.info("Starting measurement sequence...")
    # The sequencer will take control, executing each state in order.
    # The state machine will automatically return to 'Idle' when the sequence is complete.
    machine.sequencer.start(sequence)