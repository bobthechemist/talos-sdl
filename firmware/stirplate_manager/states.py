# firmware/stirplate_manager/states.py
# type: ignore
import board
from shared_lib.statemachine import State

# The correct library provided by Adafruit for this specific FeatherWing.
from adafruit_motorkit import MotorKit

class Initialize(State):
    """
    Initializes the I2C bus and the MotorKit object for the FeatherWing.
    """
    @property
    def name(self):
        return 'Initialize'

    def enter(self, machine, context=None):
        super().enter(machine, context)
        try:
            i2c = board.I2C()
            
            # --- CORRECTION IS HERE ---
            # Instantiate the correct MotorKit class from the adafruit_motorkit library.
            motor_kit = MotorKit(i2c=i2c)
            # The frequency setting is associated with the PCA9685 driver on the kit,
            # but it is not set on the kit object itself in this library.
            # We will rely on the library's default, which is typically 1600 Hz.
            
            # Create a simple list of the motor objects for easy access.
            machine.motors = [motor_kit.motor1, motor_kit.motor2, motor_kit.motor3, motor_kit.motor4]
            machine.log.info("Adafruit MotorKit initialized successfully.")

            # Ensure all motors are stopped on startup as a safety measure.
            for motor in machine.motors:
                motor.throttle = 0.0
            
            machine.log.info("All motors set to 0 speed. Transitioning to Idle.")
            machine.go_to_state('Idle')
            
        except Exception as e:
            machine.flags['error_message'] = f"Failed to initialize Adafruit MotorKit: {e}"
            machine.log.critical(machine.flags['error_message'])
            machine.go_to_state('Error')