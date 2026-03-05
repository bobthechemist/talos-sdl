# firmware/stirplate_manager/__init__.py
# type: ignore
import board
from shared_lib.statemachine import StateMachine
from shared_lib.messages import Message
from communicate.circuitpython_postman import CircuitPythonPostman

# Import resources from the common firmware library
from firmware.common.common_states import GenericIdle, GenericError
from firmware.common.command_library import register_common_commands

# Import the device-specific parts we are defining
from . import states
from . import handlers

# ============================================================================
# 1. DECLARATIVE SECTION
# ============================================================================
SUBSYSTEM_NAME = "STIRPLATE_MANAGER"
SUBSYSTEM_VERSION = "1.0.0"
SUBSYSTEM_INIT_STATE = "Initialize"

SUBSYSTEM_CONFIG = {
    "pins": {
        "SCL": board.SCL,
        "SDA": board.SDA
    },
    "motor_count": 4,
    "pwm_frequency": 1600,
    "ai_guidance": "This device controls up to 4 DC motors for stirring. Motor IDs are integers from 1 to 4. Speeds are floats from 0.0 (off) to 1.0 (full speed)."
}

# ============================================================================
# 2. ASSEMBLY SECTION
# ============================================================================

def send_telemetry(machine):
    """Callback function to generate and send the stirplate's telemetry."""
    try:
        # Build a dictionary of the current speed for each motor.
        # This is more explicit and machine-readable than a list.
        speed_data = {}
        for i in range(machine.config["motor_count"]):
            # machine.motors is a 0-indexed list of motor objects
            speed = machine.motors[i].throttle if machine.motors[i].throttle is not None else 0.0
            speed_data[f"motor_{i+1}_speed"] = round(speed, 3)

        machine.log.debug(f"Telemetry: {speed_data}")

        telemetry_message = Message.create_message(
            subsystem_name=machine.name,
            status="TELEMETRY",
            payload={
                "metadata": {"data_type": "motor_speeds"},
                "data": speed_data
            }
        )
        machine.postman.send(telemetry_message.serialize())
    except Exception as e:
        machine.log.error(f"Failed to send telemetry: {e}")

def build_status(machine):
    """Builds the instrument-specific status dictionary for the get_info command."""
    status_data = {}
    for i in range(machine.config["motor_count"]):
        speed = machine.motors[i].throttle if machine.motors[i].throttle is not None else 0.0
        status_data[f"motor_{i+1}_speed"] = round(speed, 3)
    return status_data

# --- Machine Assembly ---
machine = StateMachine(
    name=SUBSYSTEM_NAME,
    version=SUBSYSTEM_VERSION,
    config=SUBSYSTEM_CONFIG,
    init_state=SUBSYSTEM_INIT_STATE,
    status_callback=build_status
)

# Attach the communication channel
postman = CircuitPythonPostman(params={"protocol": "serial_cp"})
postman.open_channel()
machine.postman = postman

# Add all states the machine can be in
machine.add_state(states.Initialize())
machine.add_state(GenericIdle(telemetry_callback=send_telemetry))
machine.add_state(GenericError())

# Define the machine's command interface
register_common_commands(machine)
machine.add_command("set_speed", handlers.handle_set_speed, {
    "description": "Sets the speed of a single DC motor.",
    "args": [
        {"name": "motor_id", "type": "int", "description": "The motor to control (1-4)."},
        {"name": "speed", "type": "float", "description": "The speed from 0.0 (off) to 1.0 (full)."}
    ],
    "ai_enabled": True
})
machine.add_command("stop_all", handlers.handle_stop_all, {
    "description": "Immediately stops all connected motors.",
    "args": [],
    "ai_enabled": True
})

# Add machine-wide flags (dynamic runtime variables)
machine.add_flag('error_message', '')
machine.add_flag('telemetry_interval', 15.0) # Send telemetry every 15 seconds