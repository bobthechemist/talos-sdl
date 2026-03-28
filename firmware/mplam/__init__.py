# firmware/mplam/__init__.py
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
SUBSYSTEM_NAME = "MPLAM"
SUBSYSTEM_VERSION = "1.0.1" # Version updated to reflect changes
SUBSYSTEM_INIT_STATE = "Initialize"

SUBSYSTEM_CONFIG = {
    "pins": {
        "buzzer": board.GP22,
        "button_1": board.GP20,
        "button_2": board.GP21,
        "neopixel_pin": board.GP18,
        "blue_leds": [
            board.GP2, board.GP3, board.GP4, board.GP5,
            board.GP6, board.GP7, board.GP8, board.GP9,
            board.GP10, board.GP11, board.GP12, board.GP13,
            board.GP14, board.GP15
        ],
    },
    "default_brightness": 0.2,
    "max_brightness": 0.8,
    "neopixel_count": 2,
    "ai_guidance": "Use this device to signal status and to retrieve triggers from the operator. It has 2 NeoPixels (0 and 1) and 14 blue status LEDs (1-14).",
}

# ============================================================================
# 2. ASSEMBLY SECTION
# ============================================================================

def send_telemetry(machine):
    """Callback function to generate and send the MPLAM's telemetry."""
    try:
        status_led_states = [led.value for led in machine.status_leds]
        neopixel_colors = list(machine.pixels)

        telemetry_message = Message.create_message(
            subsystem_name=machine.name,
            status="TELEMETRY",
            payload={
                "metadata": {"data_type": "device_indicators"},
                "data": {
                    "status_leds": status_led_states,
                    "neopixels": neopixel_colors
                }
            }
        )
        machine.postman.send(telemetry_message.serialize())
    except Exception as e:
        machine.log.error(f"Failed to send telemetry: {e}")

def build_status(machine):
    """Builds the instrument-specific status dictionary for the get_info command."""
    return {
        "status_led_count": len(machine.status_leds),
        "neopixel_count": machine.config["neopixel_count"],
        "neopixel_brightness": machine.pixels.brightness,
        "buzzer_active": machine.buzzer.duty_cycle > 0
    }

# --- Machine Assembly ---
machine = StateMachine(
    name=SUBSYSTEM_NAME,
    version=SUBSYSTEM_VERSION,
    config=SUBSYSTEM_CONFIG,
    init_state=SUBSYSTEM_INIT_STATE,
    status_callback=build_status
)

# --- Attach Communication Channel ---
postman = CircuitPythonPostman(params={"protocol": "serial_cp"})
postman.open_channel()
machine.postman = postman

# --- Add States ---
machine.add_state(states.Initialize())
machine.add_state(states.BuzzerActive())
machine.add_state(GenericIdle(telemetry_callback=send_telemetry))
machine.add_state(GenericError())

# --- Define Command Interface ---
register_common_commands(machine)
machine.add_command("set_neopixel", handlers.handle_set_neopixel, {
    "description": "Sets the color and brightness of one of the two NeoPixels.",
    "args": [
        {"name": "pixel", "type": "int", "description": "The pixel index (0 or 1)."},
        {"name": "color", "type": "list", "description": "A list of [R, G, B] values (0-255)."},
        {"name": "brightness", "type": "float", "description": "Brightness from 0.0 to 1.0.", "default": None}
    ],
    "ai_enabled": True
})
machine.add_command("set_status", handlers.handle_set_status, {
    "description": "Turns one of the 14 blue status LEDs on or off.",
    "args": [
        {"name": "led", "type": "int", "description": "The LED number (1-14)."},
        {"name": "value", "type": "bool", "description": "True for on, False for off."}
    ],
    "ai_enabled": True
})
machine.add_command("get_status", handlers.handle_get_status, {
    "description": "Gets the on/off state of one or all blue status LEDs.",
    "args": [
        {"name": "led", "type": "int", "description": "Optional: a specific LED to query (1-14).", "default": None}
    ],
    "ai_enabled": True
})
machine.add_command("clear_all", handlers.handle_clear_all, {
    "description": "Turns off all NeoPixels, all status LEDs, and the buzzer.",
    "args": [],
    "ai_enabled": True
})
machine.add_command("set_buzzer", handlers.handle_set_buzzer, {
    "description": "Activates the buzzer at a specific frequency for a set duration.",
    "args": [
        {"name": "frequency", "type": "int", "description": "Frequency in Hz (20-20000)."},
        {"name": "duration", "type": "float", "description": "Duration in seconds (0.0-2.0)."}
    ],
    "ai_enabled": True
})

# --- AI Readiness: Disable common commands for AI Planner ---
machine.supported_commands['help']['ai_enabled'] = False
machine.supported_commands['ping']['ai_enabled'] = False
machine.supported_commands['set_time']['ai_enabled'] = False
machine.supported_commands['get_info']['ai_enabled'] = False

# --- Add machine-wide flags (dynamic runtime variables) ---
machine.add_flag('error_message', '')
machine.add_flag('telemetry_interval', 30.0) # Telemetry every 30 seconds