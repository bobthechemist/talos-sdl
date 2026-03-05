# firmware/stirplate_manager/handlers.py
# type: ignore
from shared_lib.messages import send_problem, send_success
from shared_lib.error_handling import try_wrapper
import time

@try_wrapper
def handle_set_speed(machine, payload):
    """
    Handles the 'set_speed' command. Sets a single motor's speed.
    """
    args = payload.get("args", {})
    
    # --- Guard Conditions ---
    motor_id = args.get("motor_id")
    if not isinstance(motor_id, int) or not (1 <= motor_id <= machine.config["motor_count"]):
        send_problem(machine, f"Invalid 'motor_id'. Must be an integer between 1 and {machine.config['motor_count']}.")
        return

    speed = args.get("speed")
    if not isinstance(speed, (float, int)) or not (0.0 <= speed <= 1.0):
        send_problem(machine, "Invalid 'speed'. Must be a float between 0.0 and 1.0.")
        return
        
    # --- Action ---
    target_motor = machine.motors[motor_id - 1]
    requested_speed = float(speed)
    current_speed = target_motor.throttle if target_motor.throttle is not None else 0.0

    # Get kick-start config values, using .get() for safety
    kick_enabled = machine.config.get("kick_start_enabled", False)
    kick_threshold = machine.config.get("kick_start_threshold", 0.15)

    # Condition: Only kick-start if the feature is enabled, the motor is stopped,
    # and the requested speed is low but not zero.
    if kick_enabled and current_speed == 0.0 and 0.0 < requested_speed < kick_threshold:
        
        kick_speed = machine.config.get("kick_start_speed", 0.3)
        kick_duration_sec = machine.config.get("kick_start_duration_ms", 100) / 1000.0
        
        machine.log.info(f"Kick-starting motor {motor_id} for {kick_duration_sec*1000}ms...")
        
        # The "kick"
        target_motor.throttle = kick_speed
        time.sleep(kick_duration_sec)
        
        # Settle to the requested speed
        target_motor.throttle = requested_speed
        
        machine.log.info(f"Set motor {motor_id} speed to {requested_speed} after kick-start.")
        send_success(machine, f"Motor {motor_id} speed set to {requested_speed} with a kick-start.")
        
    else:
        # Standard behavior for all other cases
        target_motor.throttle = requested_speed
        machine.log.info(f"Set motor {motor_id} speed to {requested_speed}")
        send_success(machine, f"Motor {motor_id} speed set to {requested_speed}.")

@try_wrapper
def handle_stop_all(machine, payload):
    """
    Handles the 'stop_all' command. Sets all motor throttles to 0.
    """
    for i, motor in enumerate(machine.motors):
        motor.throttle = 0.0
    
    machine.log.info("All motors stopped.")
    send_success(machine, "All motors have been stopped.")