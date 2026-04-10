# firmware/magnetometer/__init__.py
# type: ignore
import board
import neopixel
from shared_lib.statemachine import StateMachine
from shared_lib.messages import Message
from communicate.circuitpython_postman import CircuitPythonPostman

# Import resources from the common firmware library
from firmware.common.common_states import GenericIdle, GenericError
from firmware.common.command_library import register_common_commands, handle_enable_continuous, handle_read_continuous

# Import the device-specific parts we just defined
from . import states
from . import handlers

# ============================================================================
# 1. INSTRUMENT CONFIGURATION
# ============================================================================

SUBSYSTEM_NAME = "MAGNETOMETER"
SUBSYSTEM_VERSION = "1.0.0"
SUBSYSTEM_INIT_STATE = "Initialize"
SUBSYSTEM_CONFIG = {
    "pins": {
        "SCL": board.SCL,
        "SDA": board.SDA,
        "neopixel": board.NEOPIXEL
    },
    "ai_guidance": (
        "This device is a dual magnetometer probe, with an HMC5883 and TLV493 sensor. "
        "Both sensors will report magnetic field values. The HMC5883 is more sensitive "
        "but will saturate at a lower value than the TLV493 which is less sensitive "
        "and will saturate at a higher value."
    ),
}

# ============================================================================
# 2. ASSEMBLY SECTION
# ============================================================================

def send_telemetry(machine):
    """Callback function to generate and send the magnetometer's telemetry."""
    try:
        # Get readings from both sensors with offset correction
        tlv_raw_x, tlv_raw_y, tlv_raw_z = machine.tlv.magnetic
        hmc_raw_x, hmc_raw_y, hmc_raw_z = machine.hmc.magnetic

        # Apply offsets
        tlv_corrected_x = tlv_raw_x - machine.tlv_offsets['x']
        tlv_corrected_y = tlv_raw_y - machine.tlv_offsets['y']
        tlv_corrected_z = tlv_raw_z - machine.tlv_offsets['z']

        hmc_corrected_x = hmc_raw_x - machine.hmc_offsets['x']
        hmc_corrected_y = hmc_raw_y - machine.hmc_offsets['y']
        hmc_corrected_z = hmc_raw_z - machine.hmc_offsets['z']

        machine.log.debug(
            f"Telemetry: TLV493D X={tlv_corrected_x:.2f}, Y={tlv_corrected_y:.2f}, "
            f"Z={tlv_corrected_z:.2f} uT | HMC5883 X={hmc_corrected_x:.2f}, "
            f"Y={hmc_corrected_y:.2f}, Z={hmc_corrected_z:.2f} Gs"
        )

        telemetry_message = Message.create_message(
            subsystem_name=machine.name,
            status="TELEMETRY",
            payload={
                "metadata": {
                    "data_type": "magnetic_field",
                    "units": "mixed"
                },
                "data": {
                    "tlv493d": {
                        "x": round(tlv_corrected_x, 2),
                        "y": round(tlv_corrected_y, 2),
                        "z": round(tlv_corrected_z, 2)
                    },
                    "hmc5883": {
                        "x": round(hmc_corrected_x, 2),
                        "y": round(hmc_corrected_y, 2),
                        "z": round(hmc_corrected_z, 2)
                    }
                }
            }
        )
        machine.postman.send(telemetry_message.serialize())
    except Exception as e:
        machine.log.error(f"Failed to send telemetry: {e}")

def build_status(machine):
    """Builds the instrument-specific status dictionary for the get_info command."""
    return {
        "tlv493d_initialized": hasattr(machine, 'tlv'),
        "hmc5883_initialized": hasattr(machine, 'hmc'),
        "zeroed": hasattr(machine, 'tlv_offsets') and all(
            v == 0 for v in machine.tlv_offsets.values()
        ) and hasattr(machine, 'hmc_offsets') and all(
            v == 0 for v in machine.hmc_offsets.values()
        ),
        "sensor_count": 2
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
postman.open_channel()  # This should set self.channel and self.is_open
machine.postman = postman
machine.log.info(f"Postman initialized: channel={machine.postman.channel}, is_open={machine.postman.is_open}")

# --- Add States ---
machine.add_state(states.Initialize())
machine.add_state(states.Zeroing())
machine.add_state(GenericIdle(telemetry_callback=send_telemetry))
machine.add_state(GenericError())

# Add handlers from command_library
machine.handlers = {
    "enable_continuous": handle_enable_continuous,
    "read_continuous": handle_read_continuous,
    "read_now": handlers.handle_read_now,
    "zero": handlers.handle_zero,
    "set_led": handlers.handle_set_led
}

print(f"[DEBUG] Magnetometer firmware loaded with {len(machine.handlers)} handlers")

# --- Define Command Interface ---
register_common_commands(machine)

machine.add_command("read_now", handlers.handle_read_now, {
    "description": "Immediately reads both HMC5883 and TLV493 sensors and returns magnetic field values.",
    "args": [],
    "ai_enabled": True,
    "effects": ["magnetic field measurements are taken from both sensors"],
    "usage_notes": "Returns data for both sensors with offset correction applied."
})
machine.add_command("zero", handlers.handle_zero, {
    "description": "Calibrates sensors by averaging 10 readings from each sensor to remove magnetic offsets.",
    "args": [],
    "ai_enabled": True,
    "effects": ["magnetic offsets are calculated and stored for both sensors"],
    "usage_notes": "LED will blink during calibration. Takes approximately 1 second."
})
machine.add_command("set_led", handlers.handle_set_led, {
    "description": "Sets LED brightness level (0-255).",
    "args": [
        {"name": "level", "type": "int", "description": "LED brightness level [0-255]"}
    ],
    "ai_enabled": True,
    "effects": ["LED brightness is updated"]
})

# Override common commands to ensure they are not used by the AI
machine.supported_commands['help']['ai_enabled'] = False
machine.supported_commands['ping']['ai_enabled'] = False
machine.supported_commands['set_time']['ai_enabled'] = False
machine.supported_commands['get_info']['ai_enabled'] = False

# --- Add machine-wide flags (dynamic variables) ---
machine.add_flag('error_message', '')
machine.add_flag('zero_progress', 0)
machine.add_flag('zero_complete', False)