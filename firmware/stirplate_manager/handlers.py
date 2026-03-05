# firmware/stirplate_manager/handlers.py
# type: ignore
from shared_lib.messages import send_problem, send_success
from shared_lib.error_handling import try_wrapper

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
    # Convert 1-based motor_id to 0-based list index
    target_motor = machine.motors[motor_id - 1]
    target_motor.throttle = float(speed)
    
    machine.log.info(f"Set motor {motor_id} speed to {speed}")
    send_success(machine, f"Motor {motor_id} speed set to {speed}.")

@try_wrapper
def handle_stop_all(machine, payload):
    """
    Handles the 'stop_all' command. Sets all motor throttles to 0.
    """
    for i, motor in enumerate(machine.motors):
        motor.throttle = 0.0
    
    machine.log.info("All motors stopped.")
    send_success(machine, "All motors have been stopped.")