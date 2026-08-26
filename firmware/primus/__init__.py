# firmware/primus/__init__.py
#type: ignore
import board
from shared_lib.statemachine import StateMachine
from shared_lib.messages import Message
from communicate.circuitpython_postman import CircuitPythonPostman

# Import resources from common firmware library
from firmware.common.common_states import GenericError
from firmware.common.command_library import register_common_commands

# Import specific components
from . import states
from . import handlers

# ============================================================================
# 1. INSTRUMENT CONFIGURATION
# ============================================================================
SUBSYSTEM_NAME = "PRIMUS"
SUBSYSTEM_VERSION = "2.1.0"
SUBSYSTEM_INIT_STATE = "Initialize"

SUBSYSTEM_CONFIG = {
    "pins": {
        # Original Hardware
        "servo_pan": board.GP13,
        "servo_tilt": board.GP12,
        "neopixels": board.GP18,
        "buzzer": board.GP22,
        # New I2C Sensors
        "sgp30_scl": board.GP3,
        "sgp30_sda": board.GP2,
        "vl53l0x_scl": board.GP5,
        "vl53l0x_sda": board.GP4,
        "as7341_scl": board.GP17,
        "as7341_sda": board.GP16
    },
    "operational_parameters": {
        "pan_min_pulse": 700,
        "pan_max_pulse": 2300,
        "tilt_min_pulse": 500,
        "tilt_max_pulse": 2300,
        "num_pixels": 2,
        "servo_speed": 60.0  # degrees per second
    },
    "ai_guidance": (
        "The extremes of the two servo motors are not fully known and require calibration. "
        "The 'pan', 'tilt', and 'play' commands take time to execute; wait for the success response. "
        "The 'light' command accepts a 3-element list of integers for RGB color, and a pixel index (0 or 1). "
        "This version includes environmental sensors. 'read_ec02' and 'read_voc' return air quality data. "
        "'read_distance' returns distance. 'read_all' returns spectral data from the AS7341. "
        "Use 'set_gain' (e.g. 1, 2, 256), 'set_source' (0-10 mA), 'source_on' and 'source_off' to configure the AS7341."
    )
}

# ============================================================================
# 2. ASSEMBLY SECTION
# ============================================================================

def send_telemetry(machine):
    """Generates and sends telemetry message containing real-time servo angles and sensor readiness."""
    try:
        telemetry_message = Message(
            subsystem_name=machine.name,
            status="TELEMETRY",
            payload={
                "data": {
                    "pan_angle": machine.flags.get('pan_angle', 90),
                    "tilt_angle": machine.flags.get('tilt_angle', 90),
                    "sgp30_ready": machine.flags.get('sgp30_ready', False)
                }
            }
        )
        machine.postman.send(telemetry_message.serialize())
    except Exception as e:
        machine.log.error(f"Failed to generate telemetry: {e}")

def build_status(machine):
    """Builds the complete status dictionary for the get_info command."""
    return {
        "pan_angle": machine.flags.get('pan_angle', 90),
        "tilt_angle": machine.flags.get('tilt_angle', 90),
        "pixel_0_color": machine.flags.get('pixel_0_color', [0, 0, 0]),
        "pixel_1_color": machine.flags.get('pixel_1_color', [0, 0, 0]),
        "sgp30_ready": machine.flags.get('sgp30_ready', False)
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
# Injecting the CustomIdle to maintain SGP30 baseline polling
machine.add_state(states.CustomIdle(telemetry_callback=send_telemetry))
machine.add_state(GenericError())
machine.add_state(states.MoveServo())
machine.add_state(states.PlayTone())

# --- Define Command Interface ---
register_common_commands(machine)

# Original Features
machine.add_command("pan", handlers.handle_pan, {
    "description": "Moves the pan servo arm to a desired angle (0 to 180 degrees).",
    "args": [{"name": "angle", "type": "int", "description": "Target pan angle."}],
    "ai_enabled": True,
    "effects": ["arm physically pans to the new angle"]
})
machine.add_command("tilt", handlers.handle_tilt, {
    "description": "Moves the tilt servo arm to a desired angle (0 to 180 degrees).",
    "args": [{"name": "angle", "type": "int", "description": "Target tilt angle."}],
    "ai_enabled": True,
    "effects": ["arm physically tilts to the new angle"]
})
machine.add_command("light", handlers.handle_light, {
    "description": "Sets the color of one of the neopixels.",
    "args": [
        {"name": "color", "type": "list", "description": "3-element list of RGB ints (0-255)."},
        {"name": "pixel", "type": "int", "description": "Index of the neopixel (0 or 1)."}
    ],
    "ai_enabled": True,
    "effects": ["the specified neopixel immediately changes color"]
})
machine.add_command("play", handlers.handle_play, {
    "description": "Plays a tone on the buzzer for a set duration.",
    "args": [
        {"name": "frequency", "type": "int", "description": "Frequency in Hz."},
        {"name": "duration", "type": "float", "description": "Duration in seconds."}
    ],
    "ai_enabled": True,
    "effects": ["the buzzer sounds for the specified duration"]
})

# New Sensor Features with Explicit Return Schemas
machine.add_command("read_ec02", handlers.handle_read_ec02, {
    "description": "Reads the equivalent CO2 (eCO2) value from the SGP30.",
    "args": [],
    "returns": {"eCO2_ppm": {"type": "int", "unit": "ppm"}},
    "ai_enabled": True
})
machine.add_command("read_voc", handlers.handle_read_voc, {
    "description": "Reads the Total Volatile Organic Compounds (TVOC) value from the SGP30.",
    "args": [],
    "returns": {"TVOC_ppb": {"type": "int", "unit": "ppb"}},
    "ai_enabled": True
})
machine.add_command("read_distance", handlers.handle_read_distance, {
    "description": "Reads distance from the VL53L0X.",
    "args": [],
    "returns": {"distance_cm": {"type": "float", "unit": "cm"}},
    "ai_enabled": True
})
machine.add_command("read_all", handlers.handle_read_all, {
    "description": "Returns a list of all raw spectral channels from the AS7341.",
    "args": [],
    "returns": {"spectral_channels": {"type": "list[int]", "unit": "counts"}},
    "ai_enabled": True
})

# Settings
machine.add_command("set_gain", handlers.handle_set_gain, {
    "description": "Sets the AS7341 gain multiplier.",
    "args": [{"name": "multiplier", "type": "float", "description": "Allowed values: 0.5, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512"}],
    "ai_enabled": True
})
machine.add_command("set_source", handlers.handle_set_source, {
    "description": "Sets the AS7341 LED intensity.",
    "args": [{"name": "intensity", "type": "float", "description": "LED intensity in mA (0 to 10)."}],
    "ai_enabled": True
})
machine.add_command("source_on", handlers.handle_source_on, {
    "description": "Turns the AS7341 LED source ON.",
    "args": [],
    "ai_enabled": True
})
machine.add_command("source_off", handlers.handle_source_off, {
    "description": "Turns the AS7341 LED source OFF.",
    "args": [],
    "ai_enabled": True
})

# --- Override Core AI Features ---
machine.supported_commands['help']['ai_enabled'] = False
machine.supported_commands['ping']['ai_enabled'] = False
machine.supported_commands['set_time']['ai_enabled'] = False
machine.supported_commands['get_info']['ai_enabled'] = False

# --- Add Dynamic Flags ---
machine.add_flag('pan_angle', 90.0)
machine.add_flag('tilt_angle', 90.0)
machine.add_flag('pixel_0_color', [0, 0, 0])
machine.add_flag('pixel_1_color', [0, 0, 0])
machine.add_flag('sgp30_ready', False)
machine.add_flag('error_message', '')
machine.add_flag('telemetry_interval', 2.0)