# firmware/pybot_arm/__init__.py
# type: ignore
import board
from shared_lib.statemachine import StateMachine
from shared_lib.messages import Message
from communicate.circuitpython_postman import CircuitPythonPostman

# Import resources from the common firmware library
from firmware.common.common_states import GenericIdle, GenericError
from firmware.common.command_library import register_common_commands

# Import the device-specific parts we just defined
from . import states
from . import handlers

# ============================================================================
# 1. INSTRUMENT CONFIGURATION
# ============================================================================
SUBSYSTEM_NAME = "PYBOT-ARM"
SUBSYSTEM_VERSION = "1.0.0"
SUBSYSTEM_INIT_STATE = "Initialize"

# Robot constants for inverse kinematics and step conversion
ROBOT_ARM1_LENGTH = 91.61  # mm
ROBOT_ARM2_LENGTH = 105.92  # mm
M1_STEPS_PER_DEGREE = 40.0
M2_STEPS_PER_DEGREE = 64.713
M2_COMP_A1 = 34.4444
M3_STEPS_PER_MM = 396
M4_STEPS_PER_DEGREE = 8.889

SUBSYSTEM_CONFIG = {
    "pins": {
        # UART serial connection to robot arm
        "uart_tx": board.GP0,  # UART0 TX
        "uart_rx": board.GP1,  # UART0 RX
        # Optional status LED
        "indicator_led": board.LED,
    },
    "serial": {
        "baudrate": 115200,
        "timeout": 1,  # seconds
    },
    "robot_constants": {
        "arm1_length": ROBOT_ARM1_LENGTH,
        "arm2_length": ROBOT_ARM2_LENGTH,
        "m1_steps_per_degree": M1_STEPS_PER_DEGREE,
        "m2_steps_per_degree": M2_STEPS_PER_DEGREE,
        "m2_comp_a1": M2_COMP_A1,
        "m3_steps_per_mm": M3_STEPS_PER_MM,
        "m4_steps_per_degree": M4_STEPS_PER_DEGREE,
    },
    "ai_guidance": (
        "The PyBot Arm SCARA v1p2 is a 4-axis robotic arm controller connected via UART serial at 115200 baud.\n"
        "The robot uses a command/response protocol where commands are newline-terminated ASCII strings.\n"
        "The robot responds with multiline responses ending with '>' (success) or '?' (error).\n"
        "\n"
        "Key features:\n"
        "- 2 SCARA arms (Shoulder M1, Elbow M2) with inverse kinematics for XYZ positioning\n"
        "- Linear Z axis (M3) for vertical movement\n"
        "- Orientation wrist (M4) for gripper rotation\n"
        "\n"
        "Available commands:\n"
        "- 'read_sensor': Read analog sensor value from A0\n"
        "- 'initialize': Home all axes and set origin\n"
        "- 'unlock_motors': Disable motor drivers (free rotation)\n"
        "- 'move_to_xyz': Move to absolute XYZ position with wrist angle\n"
        "- 'set_speed_default': Set acceleration profile to default\n"
        "\n"
        "Important: Always check robot readiness before sending commands. "
        "The robot must be initialized before movement or sensor commands will work."
    ),
}

# ============================================================================
# 2. ASSEMBLY SECTION
# ============================================================================

def send_telemetry(machine):
    """Callback function to generate and send the pybot-arm's telemetry."""
    try:
        # Get current position data
        position = machine.flags.get('position', {"x": 0, "y": 0, "z": 0, "angle": 0})
        sensor_value = machine.flags.get('sensor_value', 0)

        machine.log.debug(f"Telemetry: Position={position}, Sensor={sensor_value}")

        telemetry_message = Message.create_message(
            subsystem_name=machine.name,
            status="TELEMETRY",
            payload={
                "metadata": {
                    "data_type": "robot_status"
                },
                "data": {
                    "position": position,
                    "sensor_value": sensor_value
                }
            }
        )
        machine.postman.send(telemetry_message.serialize())
    except Exception as e:
        machine.log.error(f"Failed to send telemetry: {e}")


def build_status(machine):
    """Builds the instrument-specific status dictionary for the get_info command."""
    return {
        "is_initialized": machine.flags.get('is_initialized', False),
        "is_ready": machine.flags.get('is_ready', False),
        "position": machine.flags.get('position', {"x": 0, "y": 0, "z": 0, "angle": 0}),
        "sensor_value": machine.flags.get('sensor_value', 0),
        "current_state": machine.state.name if hasattr(machine, 'state') and machine.state else "Unknown"
    }

# ============================================================================
# MACHINE ASSEMBLY
# ============================================================================

machine = StateMachine(
    name=SUBSYSTEM_NAME,
    version=SUBSYSTEM_VERSION,
    config=SUBSYSTEM_CONFIG,
    init_state=SUBSYSTEM_INIT_STATE,
    status_callback=build_status
)

postman = CircuitPythonPostman(params={"protocol": "serial_cp"})
postman.open_channel()
machine.postman = postman

# --- Add States ---
machine.add_state(states.Initialize())
machine.add_state(GenericIdle(telemetry_callback=send_telemetry))
machine.add_state(GenericError())
machine.add_state(states.Moving())
machine.add_state(states.ReadingSensor())

# --- Define Command Interface ---
register_common_commands(machine)

machine.add_command("read_sensor", handlers.handle_read_sensor, {
    "description": "Read analog sensor value from A0.",
    "args": [],
    "ai_enabled": True,
    "effects": ["analog sensor value is read and returned"],
    "usage_notes": "Robot must be initialized before reading sensor."
})

machine.add_command("initialize", handlers.handle_initialize, {
    "description": "Home all axes and set origin.",
    "args": [],
    "ai_enabled": True,
    "effects": ["robot axes are homed and origin is set"],
    "usage_notes": "This command must be called before any other robot movements."
})

machine.add_command("unlock_motors", handlers.handle_unlock_motors, {
    "description": "Disable motor drivers (free rotation).",
    "args": [],
    "ai_enabled": True,
    "effects": ["motor drivers are disabled, arm can be moved manually"],
    "usage_notes": "Use with caution - arm will not hold position after unlocking."
})

machine.add_command("move_to_xyz", handlers.handle_move_to_xyz, {
    "description": "Move to absolute XYZ position with wrist angle.",
    "args": [
        {"name": "x", "type": "float", "description": "Target X coordinate (mm)"},
        {"name": "y", "type": "float", "description": "Target Y coordinate (mm)"},
        {"name": "z", "type": "float", "description": "Target Z coordinate (mm)"},
        {"name": "angle", "type": "float", "description": "Wrist angle (degrees)", "default": 0}
    ],
    "ai_enabled": True,
    "effects": ["robot moves to specified XYZ position with wrist angle"],
    "usage_notes": "Coordinates must be within robot workspace. Initialize robot first."
})

machine.add_command("set_speed_default", handlers.handle_set_speed_default, {
    "description": "Set acceleration profile to default (S 340005).",
    "args": [],
    "ai_enabled": True,
    "effects": ["robot acceleration profile is set to default"],
    "usage_notes": "Recommended for normal operation."
})

# Override common commands to ensure they are not used by the AI
machine.supported_commands['help']['ai_enabled'] = False
machine.supported_commands['ping']['ai_enabled'] = False
machine.supported_commands['set_time']['ai_enabled'] = False
machine.supported_commands['get_info']['ai_enabled'] = False

# --- Add machine-wide flags (dynamic variables) ---
machine.add_flag('error_message', '')
machine.add_flag('telemetry_interval', 60.0)
machine.add_flag('is_initialized', False)
machine.add_flag('is_ready', False)
machine.add_flag('sensor_value', 0)
machine.add_flag('position', {"x": 0, "y": 0, "z": 0, "angle": 0})
machine.add_flag('working', False)
