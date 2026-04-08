# firmware/pybot_arm/states.py
# type: ignore
import time
from shared_lib.statemachine import State
from shared_lib.messages import Message, send_success, send_problem
from firmware.common.common_states import listen_for_instructions

# Import handlers module for utility functions
from . import handlers

# ============================================================================
# INITIALIZE STATE
# ============================================================================

class Initialize(State):
    """
    State: Initialize
    Purpose: Establish UART serial communication and verify robot readiness.

    Entry Actions:
    - Instantiate UART bus on board.GP0 (TX) and board.GP1 (RX) at 115200 baud
    - Send newline characters to get robot's attention

    Update Actions: Poll for '>' response to confirm robot is ready
    - Processes incoming commands while waiting for robot readiness

    On Success: Transition to Idle
    On Failure: Set error_message and transition to Error
    """
    @property
    def name(self):
        return 'Initialize'

    def enter(self, machine, context=None):
        super().enter(machine, context)

        try:
            # Import busio here for memory efficiency
            import busio

            machine.log.info("Initializing UART serial communication...")

            # Instantiate UART bus on GP0 (TX) and GP1 (RX) at 115200 baud
            machine.uart = busio.UART(tx=machine.config['pins']['uart_tx'],
                                      rx=machine.config['pins']['uart_rx'],
                                      baudrate=115200)

            # Initialize polling counters - actual polling happens in update()
            machine.flags['_init_poll_count'] = 0
            machine.flags['_init_start_time'] = time.monotonic()
            machine.flags['_init_sent_first_pings'] = False

        except Exception as e:
            machine.flags['error_message'] = f"UART init error: {e}"
            machine.log.critical(machine.flags['error_message'])
            machine.go_to_state('Error')

    def update(self, machine):
        super().update(machine)

        # Check for timeout (max 10 seconds)
        start_time = machine.flags.get('_init_start_time', time.monotonic())
        if time.monotonic() - start_time > 10.0:
            machine.flags['error_message'] = "Robot not ready after 10 seconds"
            machine.log.error(machine.flags['error_message'])
            machine.go_to_state('Error')
            return

        # Send initial pings on first update
        if not machine.flags.get('_init_sent_first_pings', False):
            machine.uart.write(b'\n')
            time.sleep(0.05)
            machine.uart.write(b'\n')
            machine.flags['_init_sent_first_pings'] = True

        # First, check for incoming commands (like 'help') before polling
        # This allows the host to query capabilities during initialization
        listen_for_instructions(machine)

        # Poll for ready status (look for '>' response)
        poll_count = machine.flags.get('_init_poll_count', 0)
        if poll_count < 10:
            machine.uart.write(b'\n')
            time.sleep(0.1)

            # Read response and check for '>' indicator
            response = self._read_response(machine)
            if self._check_ready(response):
                machine.log.info("Robot is ready!")
                machine.flags['is_ready'] = True
                # Note: is_initialized is False until the initialize command runs
                machine.flags['position'] = {"x": 0, "y": 0, "z": 0, "angle": 0}
                machine.go_to_state('Idle')
                return

            machine.flags['_init_poll_count'] = poll_count + 1
        else:
            # Small delay to avoid busy-waiting
            time.sleep(0.01)

    def _read_response(self, machine, timeout=0.5):
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

    def _check_ready(self, response):
        """Check if robot response indicates success (ends with '>')."""
        if not response:
            return False
        stripped = response.rstrip()
        if stripped:
            return stripped[-1:] == b'>'
        return False

# ============================================================================
# MOVING STATE
# ============================================================================

class Moving(State):
    """
    State: Moving
    Purpose: Execute robot movement command.

    Entry Actions:
    - Send MA (absolute move) command with 4 hex-encoded position values
    - Set working flag to True

    Internal Actions: Poll for '>' response indicating move completion

    On Success: Transition to Idle
    On Failure: Set error_message and transition to Error
    """
    @property
    def name(self):
        return 'Moving'

    def enter(self, machine, context=None):
        super().enter(machine, context)

        # Get movement parameters from context
        target = context if context else {}
        x = target.get('x', 0)
        y = target.get('y', 0)
        z = target.get('z', 0)
        angle = target.get('angle', 0)

        machine.log.info(f"Starting move to: X={x}, Y={y}, Z={z}, Angle={angle}")

        try:
            # Calculate joint angles via inverse kinematics (from handlers module)
            A1, A2 = handlers._ik(machine, x, y)
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
            cmd = "MA" + handlers._hex4d(step_A1) + handlers._hex4d(step_A2) + handlers._hex4d(step_Z) + handlers._hex4d(step_A4) + "\n"
            machine.log.debug(f"Sending command: {cmd.strip()}")

            machine.uart.write(cmd.encode())

            # Set working flag
            machine.flags['working'] = True

            # Wait for response
            self._wait_for_move_complete(machine, x, y, z, angle)

        except Exception as e:
            machine.flags['error_message'] = f"Move command error: {e}"
            machine.log.error(machine.flags['error_message'])
            send_problem(machine, f"Move failed: {e}")
            machine.go_to_state('Error')

    def _wait_for_move_complete(self, machine, x, y, z, angle, timeout=10.0):
        """Poll for '>' response indicating move completion."""
        start_time = time.monotonic()
        response = b""

        while (time.monotonic() - start_time) < timeout:
            if machine.uart.in_waiting > 0:
                data = machine.uart.read(machine.uart.in_waiting)
                if data:
                    response += data
                    machine.log.debug(f"Move response: {data}")
                    # Check for end of response
                    if response and (response.endswith(b'>') or response.endswith(b'?')):
                        break
            time.sleep(0.01)

        # Check if move was successful
        if response and response.rstrip().endswith(b'>'):
            machine.log.info(f"Move completed successfully to: X={x}, Y={y}, Z={z}, Angle={angle}")
            # Update position
            machine.flags['position'] = {"x": x, "y": y, "z": z, "angle": angle}
            machine.flags['working'] = False

            # Send DATA_RESPONSE with position
            response_msg = Message.create_message(
                subsystem_name=machine.name,
                status="DATA_RESPONSE",
                payload={
                    "metadata": {
                        "data_type": "move_position"
                    },
                    "data": {
                        "position": machine.flags['position'],
                        "message": "Move completed successfully"
                    }
                }
            )
            machine.postman.send(response_msg.serialize())

            self.task_complete = True
        else:
            machine.flags['error_message'] = "Move failed: no successful response"
            machine.log.error(machine.flags['error_message'])
            send_problem(machine, "Move failed")
            self.task_complete = True  # Mark complete so we can transition to Error

    def update(self, machine):
        super().update(machine)

# ============================================================================
# READING SENSOR STATE
# ============================================================================

class ReadingSensor(State):
    """
    State: ReadingSensor
    Purpose: Read analog sensor value from A0.

    Entry Actions:
    - Send R command to robot
    - Set working flag to True

    Internal Actions: Poll for multiline response containing sV: value

    On Success: Extract sensor value (0-1023) from sV: line, transition to Idle
    On Failure: Set error_message and transition to Error
    """
    @property
    def name(self):
        return 'ReadingSensor'

    def enter(self, machine, context=None):
        super().enter(machine, context)

        machine.log.info("Starting sensor read...")

        try:
            # Send R command to read sensor
            machine.uart.write(b'R \n')
            machine.log.debug("Sensor read command sent")

            # Set working flag
            machine.flags['working'] = True

            # Wait for response
            sensor_value = self._wait_for_sensor_read(machine)

            if sensor_value is not None:
                machine.flags['sensor_value'] = sensor_value
                machine.flags['working'] = False

                # Get current position
                position = machine.flags.get('position', {"x": 0, "y": 0, "z": 0, "angle": 0})
                machine.log.info(f"Sensor value read: {sensor_value} at position: {position}")

                # Send DATA_RESPONSE with sensor value and position
                response = Message.create_message(
                    subsystem_name=machine.name,
                    status="DATA_RESPONSE",
                    payload={
                        "metadata": {
                            "data_type": "sensor_reading"
                        },
                        "data": {
                            "sensor_value": sensor_value,
                            "position": position
                        }
                    }
                )
                machine.postman.send(response.serialize())

                self.task_complete = True
            else:
                machine.flags['error_message'] = "Sensor read failed: no valid response"
                machine.log.error(machine.flags['error_message'])
                send_problem(machine, "Sensor read failed")
                self.task_complete = True

        except Exception as e:
            machine.flags['error_message'] = f"Sensor read error: {e}"
            machine.log.error(machine.flags['error_message'])
            send_problem(machine, f"Sensor read failed: {e}")
            self.task_complete = True

    def _wait_for_sensor_read(self, machine, timeout=3.0):
        """Poll for response containing sV: value."""
        start_time = time.monotonic()
        response = b""

        while (time.monotonic() - start_time) < timeout:
            if machine.uart.in_waiting > 0:
                data = machine.uart.read(machine.uart.in_waiting)
                if data:
                    response += data
                    machine.log.debug(f"Sensor response: {data}")

                    # Check for sV: in response
                    if b'sV:' in response:
                        # Extract sensor value
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

    def update(self, machine):
        super().update(machine)
