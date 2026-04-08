# PyBot Arm SCARA v1p2 Firmware

This directory contains the CircuitPython firmware for the PyBot Arm SCARA v1p2 robotic arm.

## Overview

The PyBot Arm is a 4-axis SCARA robotic arm controlled via UART serial at 115200 baud. The robot uses a command/response protocol with multiline responses ending in '>' (success) or '?' (error).

## Features

- **2 SCARA arms** (Shoulder M1, Elbow M2) with inverse kinematics for XYZ positioning
- **Linear Z axis** (M3) for vertical movement
- **Orientation wrist** (M4) for gripper rotation
- **Analog sensor** on A0 for reading sensor values

## Available Commands

| Command | Description | AI Enabled |
|---------|-------------|------------|
| `read_sensor` | Read analog sensor value from A0 | Yes |
| `initialize` | Home all axes and set origin | Yes |
| `unlock_motors` | Disable motor drivers (free rotation) | Yes |
| `move_to_xyz` | Move to absolute XYZ position with wrist angle | Yes |
| `set_speed_default` | Set acceleration profile to default | Yes |

## File Structure

- `__init__.py` - Main entry point with configuration and state machine assembly
- `states.py` - State machine definitions (Initialize, Idle, Moving, ReadingSensor, Error)
- `handlers.py` - Command handlers for all robot operations
- `code.py` - CircuitPython boot script

## Configuration

The robot constants are defined in `__init__.py`:

```python
ROBOT_ARM1_LENGTH = 91.61  # mm
ROBOT_ARM2_LENGTH = 105.92  # mm
M1_STEPS_PER_DEGREE = 40.0
M2_STEPS_PER_DEGREE = 64.713
M2_COMP_A1 = 34.4444
M3_STEPS_PER_MM = 396
M4_STEPS_PER_DEGREE = 8.889
```

## Serial Connection

The robot connects via UART on:
- TX: board.GP0
- RX: board.GP1
- Baudrate: 115200

## Deployment

To deploy this firmware to a CircuitPython device:

```bash
python deploy.py <drive> pybot_arm
```

Where `<drive>` is the path to your CIRCUITPY drive (e.g., D: or /media/user/CIRCUITPY).
