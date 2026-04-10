# firmware/magnetometer/handlers.py
# type: ignore
import neopixel
from shared_lib.messages import Message, send_problem, send_success
from shared_lib.error_handling import try_wrapper

# ============================================================================
# COMMAND HANDLERS
# ============================================================================

@try_wrapper
def handle_read_now(machine, payload):
    """
    Handles the 'read_now' command.
    Reads both sensors and returns data with offset correction applied.
    """
    try:
        # Get raw readings from both sensors
        tlv_raw_x, tlv_raw_y, tlv_raw_z = machine.tlv.magnetic
        hmc_raw_x, hmc_raw_y, hmc_raw_z = machine.hmc.magnetic

        # Apply offsets
        tlv_corrected_x = tlv_raw_x - machine.tlv_offsets['x']
        tlv_corrected_y = tlv_raw_y - machine.tlv_offsets['y']
        tlv_corrected_z = tlv_raw_z - machine.tlv_offsets['z']

        hmc_corrected_x = hmc_raw_x - machine.hmc_offsets['x']
        hmc_corrected_y = hmc_raw_y - machine.hmc_offsets['y']
        hmc_corrected_z = hmc_raw_z - machine.hmc_offsets['z']

        machine.log.info("Read magnetometer sensors")

        response = Message.create_message(
            subsystem_name=machine.name,
            status="DATA_RESPONSE",
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
        machine.postman.send(response.serialize())
    except Exception as e:
        send_problem(machine, f"Failed to read sensors: {e}")

@try_wrapper
def handle_zero(machine, payload):
    """
    Handles the 'zero' command.
    Calibrates sensors by taking 10 readings from each sensor and averaging them.
    """
    # Accumulate values for TLV493D
    tlv_x_sum = 0
    tlv_y_sum = 0
    tlv_z_sum = 0

    # Accumulate values for HMC5883
    hmc_x_sum = 0
    hmc_y_sum = 0
    hmc_z_sum = 0

    # Take 10 measurements from each sensor
    for i in range(10):
        # Read TLV493D
        tlv_raw_x, tlv_raw_y, tlv_raw_z = machine.tlv.magnetic
        tlv_x_sum += tlv_raw_x
        tlv_y_sum += tlv_raw_y
        tlv_z_sum += tlv_raw_z

        # Read HMC5883
        hmc_raw_x, hmc_raw_y, hmc_raw_z = machine.hmc.magnetic
        hmc_x_sum += hmc_raw_x
        hmc_y_sum += hmc_raw_y
        hmc_z_sum += hmc_raw_z

        # Update progress
        machine.flags['zero_progress'] = i + 1
        machine.flags['zero_complete'] = False

        # Small delay between measurements
        import time
        time.sleep(0.05)

    # Calculate average offsets
    machine.tlv_offsets['x'] = tlv_x_sum / 10
    machine.tlv_offsets['y'] = tlv_y_sum / 10
    machine.tlv_offsets['z'] = tlv_z_sum / 10

    machine.hmc_offsets['x'] = hmc_x_sum / 10
    machine.hmc_offsets['y'] = hmc_y_sum / 10
    machine.hmc_offsets['z'] = hmc_z_sum / 10

    machine.log.info("Calibration complete:")
    machine.log.info(f"TLV493D offsets: X={machine.tlv_offsets['x']:.2f}, Y={machine.tlv_offsets['y']:.2f}, Z={machine.tlv_offsets['z']:.2f} uT")
    machine.log.info(f"HMC5883 offsets: X={machine.hmc_offsets['x']:.2f}, Y={machine.hmc_offsets['y']:.2f}, Z={machine.hmc_offsets['z']:.2f} Gs")

    machine.flags['zero_progress'] = 10
    machine.flags['zero_complete'] = True

    send_success(machine, "zero_complete")

@try_wrapper
def handle_set_led(machine, payload):
    """
    Handles the 'set_led' command.
    Sets LED brightness level (0-255).
    """
    args = payload.get("args", {})
    if not isinstance(args, dict) or "level" not in args:
        send_problem(machine, "Invalid or missing 'level' argument.")
        return

    level = args["level"]
    if not isinstance(level, int) or level < 0 or level > 255:
        send_problem(machine, "LED level must be an integer between 0 and 255.")
        return

    # Set NeoPixel brightness and color
    # machine.led.brightness = level / 255.0  # 0.0 to 1.0
    machine.led.fill((level, level, level))  # White color scaled by brightness
    machine.log.info(f"LED set to brightness: {level}/255")
    send_success(machine, f"LED brightness set to {level}")