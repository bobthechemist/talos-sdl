# Instrument Design: PyBot Arm SCARA v1p2

## 1. Instrument Overview

*   **Primary Purpose:** Control the PyBot Arm SCARA v1p2 robotic arm and read its sensor
*   **Primary Actions:** Read sensor, Move to XYZ location with wrist angle, Initialize (home), Unlock motors
*   **Periodic Telemetry Data:** Sensor value, robot position (X, Y, Z, A)
*   **Critical Failure Conditions:** Robot not ready, serial communication errors, out of workspace
*   **AI Guidance:** This is a 4-axis SCARA robotic arm controlled via UART serial at 115200 baud. The robot uses a command/response protocol with multiline responses ending in '>' (success) or '?' (error). Use inverse kinematics to convert XYZ coordinates to joint angles (A1, A2).

## 2. Hardware Configuration (`CONFIG` dictionary)

The PyBot Arm SCARA v1p2 connects via UART serial (USB) at 115200 baud. The RP2040 uses hardware UART0 on GPIO0 (TX) and GPIO1 (RX).

```python
PYBOT_ARM_CONFIG = {
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
    
    # AI Guidance: PyBot Arm SCARA v1p2 Robot Arm Controller
    "ai_guidance": """
The PyBot Arm SCARA v1p2 is a 4-axis robotic arm controller connected via UART serial at 115200 baud.
The robot uses a command/response protocol where commands are newline-terminated ASCII strings.
The robot responds with multiline responses ending with '>' (success) or '?' (error).

Key features:
- 2 SCARA arms (Shoulder M1, Elbow M2) with inverse kinematics for XYZ positioning
- Linear Z axis (M3) for vertical movement
- Orientation wrist (M4) for gripper rotation

Step conversion factors:
- M1 (Shoulder): 40.0 steps/degree
- M2 (Elbow): 64.713 steps/degree + 34.4444 compensation per M1 degree
- M3 (Z axis): 396 steps/mm
- M4 (Orientation): 8.889 steps/degree

Arm dimensions: 91.61mm (Arm1) + 105.92mm (Arm2)

Available commands:
- 'M' or 'MA' - Move (relative or absolute) with 4 position values in hex
- 'S AABBCC' - Set acceleration profile (default: S 340005)
- 'I ' - Initialize (home all axes and set origin)
- 'H[X|Y|Z][offset]' - Home specific axis
- 'C ' - Check status (returns Init:1/0, positions, sensor value)
- 'R ' - Read analog sensor on A0 (returns sV:0-1023)
- 'U ' - Unlock motors (disable drivers)

Response format: multiline with '>' or '?' at end.
Example sensor read response: 'R\\rsV:213\\r \\r\\n>\\r\\n?>'
""")
}
```

## 3. Command Interface

| `func` Name | `ai_enabled` | Description | Arguments | Success Condition | Guard Conditions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `read_sensor` | `true` | Read analog sensor value from A0 | `[]` | Returns sensor value 0-1023 | Robot must be ready |
| `initialize` | `true` | Home all axes and set origin | `[]` | Returns `Init:1` status | Robot must be ready |
| `unlock_motors` | `true` | Disable motor drivers (free rotation) | `[]` | Returns '>' response | Robot must be ready |
| `move_to_xyz` | `true` | Move to absolute XYZ position with wrist angle | `[{"name": "x", "type": "float"}, {"name": "y", "type": "float"}, {"name": "z", "type": "float"}, {"name": "angle", "type": "float"}]` | Robot reaches position | Robot must be ready; coordinates within workspace |
| `set_speed_default` | `true` | Set acceleration profile to default | `[]` | Returns '>' response | Robot must be ready |

## 4. State Definitions

#### State: `Initialize`
1.  **Purpose:** Establish UART serial communication and verify robot readiness.
2.  **Entry Actions (`enter()`):**
    *   Instantiate UART bus on `board.GP0` (TX) and `board.GP1` (RX) at 115200 baud.
    *   Wait 2 seconds for robot to reset and initialize.
    *   Send newline characters to get robot's attention.
    *   Poll for '>' response to confirm robot is ready.
3.  **Internal Actions (`update()`):** Check robot status via `getStatus()` command.
4.  **Exit Events & Triggers:**
    *   **On Success:** Trigger: Transition to `Idle`.
    *   **On Failure:** Trigger: Set `error_message` and transition to `Error`.
5.  **Exit Actions (`exit()`):** None.

#### State: `Idle`
1.  **Purpose:** Wait for movement or sensor commands.
2.  **Entry Actions (`enter()`):** None.
3.  **Internal Actions (`update()`):** None.
4.  **Exit Events & Triggers:**
    *   **On Command:** Trigger: Transition to `Moving` or `ReadingSensor`.
    *   **On Failure:** Trigger: Set `error_message` and transition to `Error`.
5.  **Exit Actions (`exit()`):** None.

#### State: `Moving`
1.  **Purpose:** Execute robot movement command.
2.  **Entry Actions (`enter()`):**
    *   Send `MA` (absolute move) or `M` (relative move) command with 4 hex-encoded position values.
    *   Set `working = True`.
3.  **Internal Actions (`update()`):** Poll for '>' response indicating move completion.
4.  **Exit Events & Triggers:**
    *   **On Success:** Trigger: Transition to `Idle`.
    *   **On Failure:** Trigger: Set `error_message` and transition to `Error`.
5.  **Exit Actions (`exit()`):** None.

#### State: `ReadingSensor`
1.  **Purpose:** Read analog sensor value from A0.
2.  **Entry Actions (`enter()`):**
    *   Send `R ` command to robot.
    *   Set `working = True`.
3.  **Internal Actions (`update()`):** Poll for multiline response containing `sV:` value.
4.  **Exit Events & Triggers:**
    *   **On Success:** Extract sensor value (0-1023) from `sV:` line, transition to `Idle`.
    *   **On Failure:** Trigger: Set `error_message` and transition to `Error`.
5.  **Exit Actions (`exit()`):** None.

#### State: `Error`
1.  **Purpose:** Handle error state when robot fails.
2.  **Entry Actions (`enter()`):**
    *   Set `error_message` with failure details.
    *   Optionally attempt recovery.
3.  **Internal Actions (`update()`):** None (wait for manual reset or auto-recovery).
4.  **Exit Events & Triggers:**
    *   **On Recovery:** Trigger: Transition to `Initialize`.
    *   **On Manual Reset:** Trigger: Transition to `Initialize`.
5.  **Exit Actions (`exit()`):** Clear `error_message`.

## 5. Instrument Class Template

```python
"""
PyBot Arm SCARA v1p2 Instrument for Talos SDL
Control a 4-axis SCARA robotic arm via UART serial at 115200 baud.
"""

import time
import busio
import board
from talos_sdl import Instrument, STATE

# Robot constants
ROBOT_ARM1_LENGTH = 91.61  # mm
ROBOT_ARM2_LENGTH = 105.92  # mm
M1_steps_per_degree = 40.0
M2_steps_per_degree = 64.713
M2_compA1 = 34.4444
M3_steps_per_mm = 396
M4_steps_per_degree = 8.889
NODATA = -20000


class PyBotArmInstrument(Instrument):
    """Instrument class for PyBot Arm SCARA v1p2 robot controller."""

    def __init__(self, config):
        super().__init__(config)
        self.ser = None
        self.ready = False
        self.working = False
        self.last_response = b""
        self.sensor_value = 0
        self.position = {"x": 0, "y": 0, "z": 0, "angle": 0}

    def _write_line(self, line: str) -> bool:
        """Write a command to the robot."""
        if not self.ser:
            return False
        try:
            self.ser.write(line.encode() + b'\n')
            time.sleep(0.01)
            return True
        except Exception as e:
            self.error_message = f"Write error: {e}"
            return False

    def _read_response(self, timeout: float = 5.0) -> bytes:
        """Read response from robot with timeout."""
        if not self.ser:
            return b""
        start_time = time.time()
        response = b""
        while (time.time() - start_time) < timeout:
            if self.ser.in_waiting > 0:
                data = self.ser.read(self.ser.in_waiting)
                if data:
                    # Print to serial terminal for debugging
                    try:
                        text = data.decode('utf-8', errors='ignore')
                        print(text, end='', flush=True)
                    except:
                        pass
                    response += data
                    # Check for end of response
                    if response and (response[-1:] == b'>' or response[-1:] == b'?'):
                        break
            time.sleep(0.01)
        self.last_response = response
        return response

    def _check_ready(self) -> bool:
        """Check if robot is ready by looking for '>' or '?' at end of response."""
        if not self.last_response:
            return False
        stripped = self.last_response.rstrip()
        if stripped and stripped[-1:] in (b'>', b'?'):
            return True
        return False

    def _hex4d(self, num: int) -> str:
        """Convert integer to 4-digit hex with sign."""
        if num < 0:
            sign = '-'
            num = -num
        else:
            sign = ' '
        return f"{sign}{num:04X}"

    def _ik(self, x: float, y: float, elbow: int = 0) -> tuple:
        """Inverse kinematics: convert XYZ to joint angles."""
        import math
        len1, len2 = ROBOT_ARM1_LENGTH, ROBOT_ARM2_LENGTH

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

    # State handlers
    def state_Initialize_enter(self):
        """Initialize UART serial and verify robot readiness."""
        try:
            self.ser = busio.UART(tx=board.GP0, rx=board.GP1, baudrate=115200)
            time.sleep(2)  # Wait for robot reset
            self.ser.write(b'\n')
            time.sleep(0.5)
            self.ser.write(b'\n')
            time.sleep(1)

            # Poll for ready status
            for _ in range(10):
                self.ser.write(b'\n')
                time.sleep(0.2)
                self._read_response(timeout=0.5)
                if self._check_ready():
                    self.ready = True
                    self.transition(STATE.IDLE)
                    return
                time.sleep(0.1)

            self.error_message = "Robot not ready after initialization"
            self.transition(STATE.ERROR)
        except Exception as e:
            self.error_message = f"UART init error: {e}"
            self.transition(STATE.ERROR)

    def state_Idle_update(self):
        """No actions in idle - wait for commands."""
        pass

    def func_read_sensor(self) -> dict:
        """Read analog sensor value from A0."""
        if not self.ready:
            return {"success": False, "error": "Robot not ready"}

        self._write_line("R ")
        self._read_response(timeout=2.0)

        # Parse sensor value from multiline response
        sensor_val = 0
        if b'sV:' in self.last_response:
            idx = self.last_response.find(b'sV:')
            if idx >= 0:
                rest = self.last_response[idx+3:]
                for newline in (b'\r', b'\n'):
                    if newline in rest:
                        rest = rest[:rest.find(newline)]
                        break
                try:
                    sensor_val = int(rest.strip())
                except:
                    pass

        self.sensor_value = sensor_val
        return {"success": True, "sensor_value": sensor_val}

    def func_initialize(self) -> dict:
        """Home all axes and set origin."""
        if not self.ready:
            return {"success": False, "error": "Robot not ready"}

        self._write_line("I ")
        self._read_response(timeout=10.0)

        if b'Init:1' in self.last_response:
            return {"success": True, "init": 1}
        return {"success": False, "error": "Initialization failed"}

    def func_unlock_motors(self) -> dict:
        """Disable motor drivers."""
        if not self.ready:
            return {"success": False, "error": "Robot not ready"}

        self._write_line("U ")
        self._read_response(timeout=2.0)

        if self._check_ready():
            return {"success": True}
        return {"success": False, "error": "Unlock failed"}

    def func_move_to_xyz(self, x: float, y: float, z: float, angle: float = 0) -> dict:
        """Move to absolute XYZ position with wrist angle."""
        if not self.ready:
            return {"success": False, "error": "Robot not ready"}

        # Calculate joint angles via inverse kinematics
        A1, A2 = self._ik(x, y)
        A4 = A1 + A2 + angle

        # Convert to steps
        step_A1 = int(A1 * M1_steps_per_degree)
        step_A2 = int(A2 * M2_steps_per_degree + A1 * M2_compA1)
        step_Z = int(z * M3_steps_per_mm)
        step_A4 = int(-A4 * M4_steps_per_degree)

        # Format and send command
        cmd = f"MA {self._hex4d(step_A1)} {self._hex4d(step_A2)} {self._hex4d(step_Z)} {self._hex4d(step_A4)}\n"
        self._write_line(cmd)
        self._read_response(timeout=10.0)

        if self._check_ready():
            self.position = {"x": x, "y": y, "z": z, "angle": angle}
            return {"success": True, "position": self.position}
        return {"success": False, "error": "Move failed"}

    def func_set_speed_default(self) -> dict:
        """Set acceleration profile to default (S 340005)."""
        if not self.ready:
            return {"success": False, "error": "Robot not ready"}

        self._write_line("S 340005")
        self._read_response(timeout=2.0)

        if self._check_ready():
            return {"success": True}
        return {"success": False, "error": "Speed setting failed"}
```