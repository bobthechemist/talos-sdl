# firmware/stirplate_manager/states.py
# type: ignore
import board
from shared_lib.statemachine import State
from adafruit_motorkit import MotorKit
from adafruit_motor import motor   

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
            frequency = machine.config.get("pwm_frequency", 1600)
            motor_kit = MotorKit(i2c=i2c, pwm_frequency=frequency)
            
            # Create a simple list of the motor objects for easy access.
            machine.motors = [motor_kit.motor1, motor_kit.motor2, motor_kit.motor3, motor_kit.motor4]
            machine.log.info(f"Adafruit MotorKit initialized successfully with PWM frequency {frequency} Hz.")

            for m in machine.motors:
                m.decay_mode = motor.SLOW_DECAY
            machine.log.info("Set all motors to SLOW_DECAY mode.")

            # Ensure all motors are stopped on startup as a safety measure.
            for m in machine.motors:
                m.throttle = 0.0
            
            machine.log.info("All motors set to 0 speed. Transitioning to Idle.")
            machine.go_to_state('Idle')
            
        except Exception as e:
            machine.flags['error_message'] = f"Failed to initialize Adafruit MotorKit: {e}"
            machine.log.critical(machine.flags['error_message'])
            machine.go_to_state('Error')