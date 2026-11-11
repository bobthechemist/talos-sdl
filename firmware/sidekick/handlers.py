# firmware/sidekick/handlers.py
# type: ignore
from shared_lib.messages import Message, send_problem, send_success
from . import kinematics
import math
from shared_lib.error_handling import try_wrapper
import re

def _execute_coordinate_move(machine, x, y, command_name, pump_arg=None):
    """
    Resolves targets to steps and triggers the sequencer for a standard move.
    """
    # 1. Resolve coordinates to physical steps
    step_targets = _resolve_coordinates_to_steps(machine, x, y, pump_arg)
    if step_targets is None:
        # The calculation helper handles logging; we report the failure here.
        send_problem(machine, f"Movement failed: target ({x}, {y}) is unreachable or out of limits.")
        return False
    
    target_m1_steps, target_m2_steps = step_targets

    # 2. Trigger the sequencer with the calculated step targets
    sequence = [{"state": "Moving"}]
    context = {
        "name": command_name,
        "target_m1_steps": target_m1_steps,
        "target_m2_steps": target_m2_steps
    }
    machine.sequencer.start(sequence, initial_context=context)
    return True

def _resolve_coordinates_to_steps(machine, x, y, pump_arg=None):
    """
    Translates coordinates and pump offsets to target step counts.
    Returns (m1_steps, m2_steps) or None if unreachable.
    """
    # 1. Solve IK to get angles
    target_angles = calculate_angles(machine, pump_arg, x, y)
    if target_angles is None:
        return None
    
    # 2. Convert angles to steps
    theta1, theta2 = target_angles
    return kinematics.degrees_to_steps(machine, theta1, theta2)

def get_current_position_steps(machine):
    """Returns the current position as a tuple of motor steps: (m1, m2)."""
    return (
        machine.flags.get('current_m1_steps', 0),
        machine.flags.get('current_m2_steps', 0)
    )

def get_current_position_degrees(machine):
    """
    Converts current motor steps to degrees.
    Returns: (theta1, theta2)
    """
    m1_steps, m2_steps = get_current_position_steps(machine)
    return kinematics.steps_to_degrees(machine, m1_steps, m2_steps)

def get_current_position_cartesian(machine):
    """
    Calculates the current Cartesian position of the arm.
    Returns: (x, y)
    """
    theta1, theta2 = _get_current_position_degrees(machine)
    return kinematics.forward_kinematics(machine, theta1, theta2)

def check_homed(machine):
    """Guard condition to ensure the device is homed."""
    if not machine.flags.get('is_homed', False):
        send_problem(machine, "Device must be homed before this operation.")
        return False
    return True

def parse_well_designation(machine, well_str: str):
    """
    Parses a well string (e.g., 'B6') into zero-based (row, column) indices.
    Returns a tuple or None if invalid.
    """
    if not isinstance(well_str, str): return None
    
    # 1. Load limits from config
    plate_geo = machine.config['plate_geometry']
    rows = plate_geo['rows']
    max_cols = plate_geo['columns']
    
    sanitized_well = well_str.upper().strip()
    
    # 2. Match the row letter(s) and any positive integer for the column
    # This regex dynamically matches any row character defined in config,
    # followed by an integer starting with 1-9 (e.g., 1, 12, 24).
    match = re.match(r'^([' + rows + r'])([1-9][0-9]*)$', sanitized_well)
    if not match: 
        return None

    letter_part = match.group(1)
    number_part = int(match.group(2))
    
    # 3. Validate column number against the configuration limit
    if number_part > max_cols:
        machine.log.warning(f"Requested column {number_part} exceeds plate limit of {max_cols}.")
        return None

    # 4. Calculate zero-based indices
    row_index = rows.find(letter_part)
    col_index = number_part - 1
    
    return (row_index, col_index)

def calculate_dispense_cycles(machine, volume, pump):
    """
    Calculates the number of cycles to perform to dispense liquid
    TODO: Consider implementing a calibrated volume instead of assuming 10 uL
    """
    increment = machine.config['pump_timings']['increment_ul']
    cycles = int(volume//increment)
    
    # Inform user if the requested volume is being adjusted
    if cycles * increment != volume:
        actual_vol = cycles * increment
        machine.log.warning(f"Volume {volume}uL is not a multiple of {increment}uL. Dispensing {actual_vol}uL.")

    if cycles <= 0:
        send_problem(machine, f"Volume {volume}uL is too low to dispense; must be at least {increment}uL.")
        return 0
    else:
        machine.log.info(f"{cycles} cycles of pump {pump} will be applied to dispense {volume} uL.")
        return cycles

def calculate_angles(machine, pump_key, target_x, target_y):
    """
    Returns angles needed for centering the end effector or a pump over the designated target
    """

    # Determine if centering the end effector or a pump
    pump = None
    if pump_key is not None and pump_key != 0 and pump_key != "0":
        # A number (1,2,3,4) or pump string ("p1", "p2", "p3", "p4") is valid
        pump = f"p{pump_key}" if isinstance(pump_key,int) else str(pump_key).lower()

    if pump:
        # If offsets cannot be found, then bail since pump_key was not valid
        pump_offset = machine.config['pump_offsets'].get(pump)
        dx = pump_offset['dx']
        dy = pump_offset['dy']
        if pump_offset is None:
            send_problem(machine, f"Invalid pump specified: '{pump_key}'.")
            return None
        
        # Pump Offset logic: Guess and Refine
        machine.log.info(f"Starting 2-pass move for pump '{pump}'...")
        machine.log.info(f" -> Estimating orientation for center ({target_x}, {target_y}).")
        guessed_angles = kinematics.inverse_kinematics(machine, target_x, target_y)
        if guessed_angles is None:
            send_problem(machine, "Target position is likely unreachable (IK Pass 1 failed).")
            return None
        
        _theta1_guess, theta2_guess = guessed_angles
        machine.log.info(f" -> Estimated orientation angle (theta2) = {theta2_guess:.2f} degrees.")

        orientation_rad = math.radians(theta2_guess)
        cos_theta = math.cos(orientation_rad)
        sin_theta = math.sin(orientation_rad)

        x_offset_rotated = dx * cos_theta - dy * sin_theta
        y_offset_rotated = dx * sin_theta + dy * cos_theta

        x_center_target = target_x + x_offset_rotated
        y_center_target = target_y + y_offset_rotated

        machine.log.info(f" -> Corrected center target is ({x_center_target:.3f}, {y_center_target:.3f}).")
        machine.log.info(f"Solving final IK for corrected center target.")
        target_angles = kinematics.inverse_kinematics(machine, x_center_target, y_center_target)
    else:
        machine.log.info(f"IK request for (x={target_x}, y={target_y})...")
        target_angles = kinematics.inverse_kinematics(machine, target_x, target_y)

    # Log an error but carry on
    if target_angles is None:
        machine.log.error("Inverse kinematics failed at end of `calculate_angles`")
    
    return target_angles


# ============================================================================
# COMMAND HANDLERS
# ============================================================================

@try_wrapper    
def handle_home(machine, payload):
    # Monolithic and needs updating, but this method works, so refactoring not a high priority
    machine.log.info("Home command received.")
    machine.go_to_state('Homing')

@try_wrapper
def handle_park(machine, payload):
    """
    Moves the arm to the pre-configured safe park position defined in homing_settings.
    """
    # 1. Guard Condition: Check if homed
    if not check_homed(machine):
        return

    # 2. Retrieve coordinates from config
    park_x = machine.config['homing_settings']['park_move_x']
    park_y = machine.config['homing_settings']['park_move_y']

    machine.log.info(f"Park command accepted. Targeting coordinates: ({park_x}, {park_y})")

    _execute_coordinate_move(machine, park_x,park_y, "park")

@try_wrapper
def handle_waste(machine, payload):
    """
    Moves the arm to the pre-configured waste position defined in waste_position config.
    """
    # 1. Guard Condition: Check if homed
    if not check_homed(machine):
        return

    # 2. Retrieve coordinates from config
    waste_config = machine.config.get('waste_position', {})
    waste_x = waste_config.get('x', 8.9) # Default is X used in initial creation of function
    waste_y = waste_config.get('y', -9.2) # Defaults is Y used in initial creation of function

    machine.log.info(f"Waste command accepted. Targeting coordinates: ({waste_x}, {waste_y})")

    _execute_coordinate_move(machine, waste_x, waste_y, "waste")

@try_wrapper
def handle_move_to(machine, payload):
    """
    Handles the high-level 'move_to' command. It uses inverse kinematics
    to convert Cartesian coordinates into motor steps.
    No calibration is performed with this routine. Position is where the sidekick 
    thinks the world coordinates are.
    """
    # 1. Guard Condition: Check if homed
    if not check_homed(machine):
        return

    # 2. Extract and Validate Input Arguments
    args = payload.get("args", {})

    target_x = args.get("x")
    target_y = args.get("y")
    pump_arg = args.get("pump")

    if target_x is None or target_y is None:
        send_problem(machine, "Missing 'x' or 'y' in command arguments.")
        return

    try:
        target_x = float(target_x)
        target_y = float(target_y)
    except ValueError:
        send_problem(machine, "Invalid coordinate format; 'x' and 'y' must be numbers.")
        return

    _execute_coordinate_move(machine, target_x, target_y, "move_to", pump_arg)

@try_wrapper
def handle_move_rel(machine, payload):
    """
    Handles the 'move_rel' command. Moves the arm relative to its
    current position by a Cartesian offset (dx, dy).
    """
    # 1. Guard Condition: Check if homed
    if not check_homed(machine):
        return

    # 2. Extract and Validate Input Arguments
    args = payload.get("args", {})
    dx = args.get("dx")
    dy = args.get("dy")

    if dx is None or dy is None:
        send_problem(machine, "Missing 'dx' or 'dy' in command arguments.")
        return

    try:
        dx = float(dx)
        dy = float(dy)
    except ValueError:
        send_problem(machine, "Invalid offset format; 'dx' and 'dy' must be numbers.")
        return

    # 3. Get Current Cartesian Position using Forward Kinematics
    # This is the key step for a relative move.
    current_m1_steps = machine.flags.get('current_m1_steps', 0)
    current_m2_steps = machine.flags.get('current_m2_steps', 0)
    
    current_theta1, current_theta2 = kinematics.steps_to_degrees(machine, current_m1_steps, current_m2_steps)
    x_current, y_current = kinematics.forward_kinematics(machine, current_theta1, current_theta2)
    
    machine.log.info(f"Current position: ({x_current:.3f}, {y_current:.3f})cm. Applying offset ({dx}, {dy}).")

    # 4. Calculate Target Cartesian Position
    x_target = x_current + dx
    y_target = y_current + dy

    _execute_coordinate_move(machine, x_target, y_target, "move_rel")

#@try_wrapper
def handle_dispense(machine, payload):
    """
    Dispenses a specified volume from a pump at the current arm location.
    This command uses the state sequencer to execute the dispense action.
    """
    if not check_homed(machine): return
    
    # 1. Extract and Validate Arguments
    args = payload.get('args',{})
    pump = args.get('pump')
    vol = args.get('vol',None)
    
    if pump not in machine.config['pump_offsets']:
        valid_pumps = list(machine.config["pump_offsets"].keys())
        send_problem(machine, f"Invalid pump specified: {pump}. Choose from {valid_pumps}")
        return

    if vol is None:
        send_problem(machine, "Missing 'vol' in command arguments.")
        return

    # 2. Calculate Dispense Cycles
    cycles = calculate_dispense_cycles(machine, vol, pump)
        
    # 3. Set Context and Start the Sequencer
    machine.log.info(f"Dispense command accepted for pump {pump}, {cycles} cycles.")
    
    sequence = [{"state": "Dispensing"}]
    context = {
        "name": "dispense",
        "dispense_pump": pump,
        "dispense_cycles": cycles
    }
    machine.sequencer.start(sequence, initial_context=context)

#@try_wrapper
def handle_dispense_at(machine, payload):
    """
    Moves a specific pump tip to an absolute (x, y) coordinate, then
    dispenses a specified volume. This is a multi-step sequence.
    """
    if not check_homed(machine): return

    # 1. Extract and Validate All Arguments
    args = payload.get("args", {})
    target_x = args.get("x")
    target_y = args.get("y")
    pump_arg = args.get("pump")
    vol = args.get("vol")
    # Handle the two accepted forms (str|int) of pump argument
    pump = f"p{pump_arg}" if isinstance(pump_arg,int) else str(pump_arg).lower()

    if target_x is None or target_y is None or pump_arg is None or vol is None:
        send_problem(machine, "Missing 'x', 'y', 'pump', or 'vol' in command arguments.")
        return

    pump_offset = machine.config['pump_offsets'].get(pump)
    if pump_offset is None:
        send_problem(machine, f"Invalid pump key '{pump}'.")
        return

    # Perform Inverse Kinematics
    machine.log.info(f"IK request from dispense_at for (x={target_x}, y={target_y}, pump={pump})...")
    target_angles = calculate_angles(machine, pump, target_x, target_y)
    
    if target_angles is None:
        send_problem(machine, "Target position is unreachable (IK Pass 2 failed).")
        return
    
    theta1, theta2 = target_angles
    target_m1_steps, target_m2_steps = kinematics.degrees_to_steps(machine, theta1, theta2)
    machine.log.info(f"IK success. Target: ({theta1:.2f}, {theta2:.2f}) degrees -> ({target_m1_steps}, {target_m2_steps}) steps.")

    # --- 3. Calculate the Dispense (Logic from handle_dispense) ---
    cycles = calculate_dispense_cycles(machine, vol, pump)

    # --- 4. Build the Sequence and Context ---
    # The context must contain ALL information needed for ALL steps in the sequence.
    machine.log.info(f"Dispense_at command accepted. Moving tip {pump} to ({target_x}, {target_y}) then dispensing {cycles} cycles.")
    
    sequence = [
        {"state": "Moving"},
        {"state": "Dispensing"}
    ]
    context = {
        "name": "dispense_at",
        # Parameters for the 'Moving' state
        "target_m1_steps": target_m1_steps,
        "target_m2_steps": target_m2_steps,
        # Parameters for the 'Dispensing' state
        "dispense_pump": pump,
        "dispense_cycles": cycles
    }

    # --- 5. Start the Sequencer ---
    machine.sequencer.start(sequence, initial_context=context)

@try_wrapper
def handle_steps(machine, payload):
    """
    Handles the low-level 'steps' command for relative motor movement.
    """
    # Must be homed to work properly
    if not check_homed(machine): return

    # 1. Extract and Validate Arguments
    args = payload.get("args", {})
    m1_rel_steps = args.get("m1", 0)
    m2_rel_steps = args.get("m2", 0)

    try:
        m1_rel_steps = int(m1_rel_steps)
        m2_rel_steps = int(m2_rel_steps)
    except (ValueError, TypeError):
        send_problem(machine, "Invalid step format; 'm1' and 'm2' must be integers.")
        return

    # 2. Calculate the absolute target position from the current position
    current_m1 = machine.flags.get('current_m1_steps', 0)
    current_m2 = machine.flags.get('current_m2_steps', 0)
    
    target_m1 = current_m1 + m1_rel_steps
    target_m2 = current_m2 + m2_rel_steps

    machine.log.info(f"Steps command accepted. Moving relatively by ({m1_rel_steps}, {m2_rel_steps}) to absolute ({target_m1}, {target_m2}).")
    
    # 3. Set Context and Start the Sequencer
    sequence = [{"state": "Moving"}]
    context = {
        "name": "steps",
        "target_m1_steps": target_m1,
        "target_m2_steps": target_m2
    }
    machine.sequencer.start(sequence, initial_context=context)

def handle_to_well(machine, payload):
    """
    Moves end effector to a specified well on a 96-well plate using a fixed A1 offset.
    """
    if not check_homed(machine):
        return

    # 1. Extract and Validate Arguments
    args = payload.get("args", {})
    well_designation = args.get("well")
    pump_arg = args.get("pump") # Can be None, 0, 1, "p1", etc.

    if well_designation is None:
        send_problem(machine, "Missing required 'well' argument.")
        return

    # 2. Parse well designation to grid indices
    parsed_indices = parse_well_designation(machine, well_designation)
    if parsed_indices is None:
        send_problem(machine, f"Invalid 'well' designation: '{well_designation}'.")
        return
    row_idx, col_idx = parsed_indices

    # 3. Calculate Well Coordinates (Plate Relative)
    pitch = machine.config['plate_geometry']['well_pitch_cm']
    
    # Note: Ensure these axes match your physical setup. 
    # Based on previous code: x=Rows, y=Cols
    well_x_rel = row_idx * pitch
    well_y_rel = col_idx * pitch
    
    # 4. Apply A1 Offset (Transform to World Coordinates)
    a1_offset = machine.config.get('A1_offset', {'dx': 0, 'dy': 0})
    target_x = well_x_rel + a1_offset['dx']
    target_y = well_y_rel + a1_offset['dy']

    machine.log.info(f"Targeting '{well_designation}': Rel({well_x_rel:.2f}, {well_y_rel:.2f}) -> World({target_x:.2f}, {target_y:.2f})")

    _execute_coordinate_move(machine, target_x, target_y, "to_well", pump_arg)


def handle_to_well_with_pumps(machine, payload):
    """
    Moves the end effector or a specific pump to a specified well using fixed A1 offset.
    Optionally dispenses if 'vol' is provided.
    """
    if not check_homed(machine):
        return

    # 1. Extract and Validate Arguments
    args = payload.get("args", {})
    well_designation = args.get("well")
    pump_arg = args.get("pump") 
    vol = args.get("vol")

    if well_designation is None:
        send_problem(machine, "Missing required 'well' argument.")
        return
    
    if vol is not None and pump_arg is None:
        send_problem(machine, "Missing 'pump' argument; required when 'vol' is provided.")
        return

    # 2. Parse well designation
    parsed_indices = parse_well_designation(machine, well_designation)
    if parsed_indices is None:
        send_problem(machine, f"Invalid 'well' designation: '{well_designation}'.")
        return
    row_idx, col_idx = parsed_indices

    # 3. Calculate Target Coordinates (World Space)
    pitch = machine.config['plate_geometry']['well_pitch_cm']
    a1_offset = machine.config.get('A1_offset', {'dx': 0, 'dy': 0})
    
    target_x = (row_idx * pitch) + a1_offset['dx']
    target_y = (col_idx * pitch) + a1_offset['dy']

    machine.log.info(f"Targeting '{well_designation}': World({target_x:.2f}, {target_y:.2f})")

    # 4. Inverse Kinematics
    target_angles = calculate_angles(machine, pump_arg, target_x, target_y)
    if target_angles is None:
        send_problem(machine, "Inverse kinematics failed. Target may be unreachable.")
        return
    
    theta1, theta2 = target_angles
    target_m1_steps, target_m2_steps = kinematics.degrees_to_steps(machine, theta1, theta2)

    # 5. Build Sequence (Move only OR Move + Dispense)
    if vol is not None:
        pump = f"p{pump_arg}" if isinstance(pump_arg, int) else str(pump_arg).lower()
        cycles = calculate_dispense_cycles(machine, vol, pump)
        
        if cycles <= 0: return # Error already sent by calc function

        sequence = [
            {"state": "Moving"},
            {"state": "Dispensing"}
        ]
        context = {
            "name": "to_well_and_dispense",
            "target_m1_steps": target_m1_steps,
            "target_m2_steps": target_m2_steps,
            "dispense_pump": pump,
            "dispense_cycles": cycles
        }
    else:
        sequence = [{"state": "Moving"}]
        context = {
            "name": "to_well",
            "target_m1_steps": target_m1_steps,
            "target_m2_steps": target_m2_steps
        }

    machine.sequencer.start(sequence, initial_context=context)
