# firmware/pybot_arm/handlers.py
# type: ignore
import time
from shared_lib.messages import Message, send_problem, send_success
from shared_lib.error_handling import try_wrapper

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _ik(machine, x, y, elbow=0):
    """
    Inverse kinematics: convert XYZ to joint angles.

    Args:
        machine: The state machine instance (for config access)
        x: Target X coordinate (mm)
        y: Target Y coordinate (mm)
        elbow: Elbow configuration (0 = normal, 1 = flipped)

    Returns:
        tuple: (A1, A2) joint angles in degrees
    """
    import math

    constants = machine.config.get('robot_constants', {})
    len1 = constants.get('arm1_length', 91.61)  # mm
    len2 = constants.get('arm2_length', 105.92)  # mm

    if elbow == 1:
        x = -x

    dist = math.sqrt(x*x + y*y)
    if dist > (len1 + len2):
        dist = (len1 + len2) - 0.001

    D1 = math.atan2(y, x)
    try:
        D2 = math.acos((dist*dist + len1*len1 - len2*len2) / (2.0 * dist*len1))
    except ValueError:
        D2 = 0

    A1 = math.degrees(D1 + D2) - 90
    A2 = math.acos((len1*len1 + len2*len2 - dist*dist) / (2.0 * len1*len2))
    A2 = math.degrees(A2) - 180

    if elbow == 1:
        A1 = -A1
        A2 = -A2

    return A1, A2


def _hex4d(num):
    """Convert integer to 4-digit hex with sign."""
    if num < 0:
        sign = '-'
        num = -num
    else:
        sign = ' '
    return f"{sign}{num:04X}"


def _read_response(machine, timeout=5.0):
    """Read response from robot with timeout."""
    if not hasattr(machine, 'uart') or machine.uart is None:
        return b""

    start_time = time.monotonic()
    response = b""

    while (time.monotonic() - start_time) < timeout:
        if machine.uart.in_waiting > 0:
            data = machine.uart.read(machine.uart.in_waiting)
            if data:
                response += data
                # Check for end of response
                if response and (response.endswith(b'>') or response.endswith(b'?')):
                    break
        time.sleep(0.01)

    return response


def _check_ready(response):
    """Check if robot response indicates success (ends with '>')."""
    if not response:
        return False
    stripped = response.rstrip()
    if stripped:
        return stripped[-1:] == b'>'
    return False


def _wait_for_sensor_read(machine, timeout=3.0):
    """Poll for response containing sV: value."""
    start_time = time.monotonic()
    response = b""

    while (time.monotonic() - start_time) < timeout:
        if machine.uart.in_waiting > 0:
            data = machine.uart.read(machine.uart.in_waiting)
            if data:
                response += data

                # Check for sV: in response
                if b'sV:' in response:
                    idx = response.find(b'sV:')
                    if idx >= 0:
                        rest = response[idx + 3:]
                        # Find end of value (newline or space)
                        for newline in (b'\r', b'\n', b' '):
                            if newline in rest:
                                rest = rest[:rest.find(newline)]
                                break
                        try:
                            sensor_value = int(rest.strip())
                            return sensor_value
                        except (ValueError, TypeError):
                            machine.log.error(f"Could not parse sensor value from: {rest}")

        time.sleep(0.01)

    return None

# ============================================================================
# COMMAND HANDLERS
# ============================================================================

@try_wrapper
def handle_read_sensor(machine, payload):
    """
    Handles the 'read_sensor' command.
    Reads analog sensor value from A0.
    """
    # Check if robot is ready
    if not machine.flags.get('is_ready', False):
        send_problem(machine, "Robot not ready. Please initialize first.")
        return

    # Set working flag
    machine.flags['working'] = True

    try:
        # Send R command to read sensor
        machine.uart.write(b'R \n')

        # Wait for response
        sensor_value = _wait_for_sensor_read(machine)

        if sensor_value is not None:
            machine.flags['sensor_value'] = sensor_value
            machine.flags['working'] = False

            # Send DATA_RESPONSE with sensor value
            response = Message.create_message(
                subsystem_name=machine.name,
                status="DATA_RESPONSE",
                payload={
                    "metadata": {
                        "data_type": "sensor_reading"
                    },
                    "data": {
                        "sensor_value": sensor_value
                    }
                }
            )
            machine.postman.send(response.serialize())
            machine.log.info(f"Sensor value read: {sensor_value}")
        else:
            machine.flags['working'] = False
            send_problem(machine, "Sensor read failed: no valid response")
            machine.log.error("Sensor read failed: no valid response")

    except Exception as e:
        machine.flags['working'] = False
        send_problem(machine, f"Sensor read failed: {e}")
        machine.log.error(f"Sensor read failed: {e}")


@try_wrapper
def handle_initialize(machine, payload):
    """
    Handles the 'initialize' command.
    Homes all axes and sets origin.
    """
    print("[PYBOT-ARM DEBUG] handle_initialize called")
    print(f"[PYBOT-ARM DEBUG] is_ready flag: {machine.flags.get('is_ready', False)}")

    # Check if robot is ready
    if not machine.flags.get('is_ready', False):
        print("[PYBOT-ARM DEBUG] Robot not ready, sending problem")
        send_problem(machine, "Robot not ready. Please initialize first.")
        return

    # Set working flag
    machine.flags['working'] = True
    print("[PYBOT-ARM DEBUG] Sending I command to robot")

    try:
        # Send I command to initialize/homing
        machine.uart.write(b'I \n')
        time.sleep(0.1)  # Give robot time to process

        # Wait for response (homing may take longer)
        print("[PYBOT-ARM DEBUG] Waiting for robot response...")
        response = _read_response(machine, timeout=20.0)

        # Debug print - convert to string first to avoid f-string issues
        print("[PYBOT-ARM DEBUG] Raw response:", response)
        print("[PYBOT-ARM DEBUG] Response type:", type(response))
        print("[PYBOT-ARM DEBUG] Response length:", len(response))

        # Convert response to string for checking
        if response:
            try:
                response_str = response.decode('utf-8')
            except:
                # Fallback for CircuitPython which may not support errors argument
                response_str = str(response)
        else:
            response_str = ""
        print("[PYBOT-ARM DEBUG] Response as string:", response_str)

        # Check for success - robot may respond with different success indicators
        # Common patterns: '>', 'Init:1', 'OK', or 'Done'
        success_found = False
        if b'Init:1' in response:
            print("[PYBOT-ARM DEBUG] Found Init:1 - classic success indicator")
            success_found = True
        elif response and response.rstrip().endswith(b'>'):
            print("[PYBOT-ARM DEBUG] Response ends with > - success indicator")
            success_found = True
        elif 'Init:1' in response_str:
            print("[PYBOT-ARM DEBUG] Found Init:1 in string response")
            success_found = True
        elif 'OK' in response_str or 'Done' in response_str:
            print("[PYBOT-ARM DEBUG] Found OK/Done - success indicator")
            success_found = True
        else:
            print("[PYBOT-ARM DEBUG] No success indicator found")

        if success_found:
            machine.flags['is_initialized'] = True
            machine.flags['is_ready'] = True
            machine.flags['position'] = {"x": 0, "y": 0, "z": 0, "angle": 0}
            machine.flags['working'] = False
            send_success(machine, "Initialization completed successfully")
            machine.log.info("Initialization completed successfully")
        else:
            machine.flags['working'] = False
            send_problem(machine, "Initialization failed: unexpected response. Expected Init:1 or '>', got: " + response_str)
            machine.log.error("Initialization failed. Full response: " + response_str)

    except Exception as e:
        error_msg = str(e)
        print("[PYBOT-ARM DEBUG] Exception during initialize:", error_msg)
        machine.flags['working'] = False
        send_problem(machine, "Initialization failed: " + error_msg)
        machine.log.error("Initialization failed: " + error_msg)


@try_wrapper
def handle_unlock_motors(machine, payload):
    """
    Handles the 'unlock_motors' command.
    Disables motor drivers (free rotation).
    """
    # Check if robot is ready
    if not machine.flags.get('is_ready', False):
        send_problem(machine, "Robot not ready. Please initialize first.")
        return

    # Set working flag
    machine.flags['working'] = True

    try:
        # Send U command to unlock motors
        machine.uart.write(b'U \n')

        # Wait for response
        response = _read_response(machine, timeout=5.0)

        if _check_ready(response):
            machine.flags['working'] = False
            machine.flags['is_initialized'] = False  # Motors unlocked, so not initialized
            send_success(machine, "Motors unlocked successfully")
            machine.log.info("Motors unlocked successfully")
        else:
            machine.flags['working'] = False
            send_problem(machine, "Unlock motors failed")
            machine.log.error("Unlock motors failed")

    except Exception as e:
        machine.flags['working'] = False
        send_problem(machine, f"Unlock motors failed: {e}")
        machine.log.error(f"Unlock motors failed: {e}")


@try_wrapper
def handle_move_to_xyz(machine, payload):
    """
    Handles the 'move_to_xyz' command.
    Moves to absolute XYZ position with wrist angle.
    """
    # Check if robot is ready
    if not machine.flags.get('is_ready', False):
        send_problem(machine, "Robot not ready. Please initialize first.")
        return

    # Get arguments from payload
    args = payload.get('args', {})
    x = args.get('x', 0)
    y = args.get('y', 0)
    z = args.get('z', 0)
    angle = args.get('angle', 0)

    # Validate coordinates are within workspace (basic check)
    # PyBot Arm SCARA workspace approximately 200mm radius
    import math
    dist = math.sqrt(x*x + y*y)
    max_radius = 200  # mm - approximate workspace radius
    if dist > max_radius:
        send_problem(machine, f"Target position ({x}, {y}) is outside workspace (max radius: {max_radius}mm)")
        return

    # Set working flag
    machine.flags['working'] = True

    try:
        # Calculate joint angles via inverse kinematics
        A1, A2 = _ik(machine, x, y)
        A4 = A1 + A2 + angle

        # Get step conversion constants
        constants = machine.config.get('robot_constants', {})
        m1_steps_per_degree = constants.get('m1_steps_per_degree', 40.0)
        m2_steps_per_degree = constants.get('m2_steps_per_degree', 64.713)
        m2_comp_a1 = constants.get('m2_comp_a1', 34.4444)
        m3_steps_per_mm = constants.get('m3_steps_per_mm', 396)
        m4_steps_per_degree = constants.get('m4_steps_per_degree', 8.889)

        # Convert to steps
        step_A1 = int(A1 * m1_steps_per_degree)
        step_A2 = int(A2 * m2_steps_per_degree + A1 * m2_comp_a1)
        step_Z = int(z * m3_steps_per_mm)
        step_A4 = int(-A4 * m4_steps_per_degree)

        # Format and send command using MA (absolute move)
        # Match format from PyBotArm_SCARA_v1p2.py: MA + 4x 5-char params + newline
        cmd = "MA" + _hex4d(step_A1) + _hex4d(step_A2) + _hex4d(step_Z) + _hex4d(step_A4) + "\n"
        machine.log.debug(f"Sending move command: {cmd.strip()}")

        machine.uart.write(cmd.encode())

        # Wait for response
        response = _read_response(machine, timeout=15.0)

        if _check_ready(response):
            machine.flags['position'] = {"x": x, "y": y, "z": z, "angle": angle}
            machine.flags['working'] = False
            send_success(machine, "Move completed successfully")
            machine.log.info(f"Move completed to: X={x}, Y={y}, Z={z}, Angle={angle}")
        else:
            machine.flags['working'] = False
            send_problem(machine, "Move failed: no successful response")
            machine.log.error("Move failed: no successful response")

    except Exception as e:
        machine.flags['working'] = False
        send_problem(machine, f"Move failed: {e}")
        machine.log.error(f"Move failed: {e}")


@try_wrapper
def handle_set_speed_default(machine, payload):
    """
    Handles the 'set_speed_default' command.
    Sets acceleration profile to default (S 340005).
    """
    # Check if robot is ready
    if not machine.flags.get('is_ready', False):
        send_problem(machine, "Robot not ready. Please initialize first.")
        return

    # Set working flag
    machine.flags['working'] = True

    try:
        # Send S 340005 command for default acceleration
        machine.uart.write(b'S 340005\n')

        # Wait for response
        response = _read_response(machine, timeout=5.0)

        if _check_ready(response):
            machine.flags['working'] = False
            send_success(machine, "Speed profile set to default (S 340005)")
            machine.log.info("Speed profile set to default")
        else:
            machine.flags['working'] = False
            send_problem(machine, "Speed setting failed")
            machine.log.error("Speed setting failed")

    except Exception as e:
        machine.flags['working'] = False
        send_problem(machine, f"Speed setting failed: {e}")
        machine.log.error(f"Speed setting failed: {e}")
