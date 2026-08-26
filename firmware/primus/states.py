# firmware/primus/states.py
#type: ignore
import board
import time
import pwmio
import neopixel
import busio
import bitbangio
from adafruit_motor import servo
import adafruit_sgp30
import adafruit_vl53l0x
import adafruit_as7341

from shared_lib.statemachine import State, ContextError
from firmware.common.common_states import GenericIdle

# ============================================================================
# PRIMARY SYSTEM STATES
# ============================================================================

class Initialize(State):
    """
    Initializes hardware pins for old payloads and the new sensors. 
    Applies a non-blocking 15-second warmup for the SGP30 inside the update cycle.
    """
    @property
    def name(self): return 'Initialize'

    def enter(self, machine, context=None):
        super().enter(machine, context)
        try:
            machine.hardware = {}
            config = machine.config
            op_params = config['operational_parameters']
            pins = config['pins']
            
            # 1. Initialize Servos
            pwm_pan = pwmio.PWMOut(pins['servo_pan'], duty_cycle=2 ** 15, frequency=50)
            machine.hardware['servo_pan'] = servo.Servo(
                pwm_pan, min_pulse=op_params['pan_min_pulse'], max_pulse=op_params['pan_max_pulse']
            )
            
            pwm_tilt = pwmio.PWMOut(pins['servo_tilt'], duty_cycle=2 ** 15, frequency=50)
            machine.hardware['servo_tilt'] = servo.Servo(
                pwm_tilt, min_pulse=op_params['tilt_min_pulse'], max_pulse=op_params['tilt_max_pulse']
            )
            
            # 2. Initialize Neopixels
            pixels = neopixel.NeoPixel(pins['neopixels'], op_params['num_pixels'], auto_write=True)
            machine.hardware['pixels'] = pixels
            
            # 3. Initialize Buzzer
            buzzer = pwmio.PWMOut(pins['buzzer'], duty_cycle=0, frequency=440, variable_frequency=True)
            machine.hardware['buzzer'] = buzzer
            
            # 4. Initialize New Sensors
            # SGP30 (Grove 2)
            i2c_sgp30 = busio.I2C(scl=pins['sgp30_scl'], sda=pins['sgp30_sda'])
            machine.hardware['sgp30'] = adafruit_sgp30.Adafruit_SGP30(i2c_sgp30)
            machine.hardware['sgp30'].iaq_init()
            
            # VL53L0X (Grove 3)
            i2c_vl53l0x = busio.I2C(scl=pins['vl53l0x_scl'], sda=pins['vl53l0x_sda'])
            machine.hardware['vl53l0x'] = adafruit_vl53l0x.VL53L0X(i2c_vl53l0x)
            
            # AS7341 (Grove 4 - Requires BitBang)
            i2c_as7341 = bitbangio.I2C(scl=pins['as7341_scl'], sda=pins['as7341_sda'])
            machine.hardware['as7341'] = adafruit_as7341.AS7341(i2c_as7341)
            
            # 5. Set Hardware Defaults
            machine.hardware['servo_pan'].angle = 90
            machine.flags['pan_angle'] = 90.0
            
            machine.hardware['servo_tilt'].angle = 90
            machine.flags['tilt_angle'] = 90.0
            
            pixels.fill((0, 0, 0))
            machine.flags['pixel_0_color'] = [0, 0, 0]
            machine.flags['pixel_1_color'] = [0, 0, 0]
            machine.flags['sgp30_ready'] = False
            
            # Timing variables for the SGP30 warmup (non-blocking)
            self.start_time = time.monotonic()
            self.last_sgp_read = 0.0
            
            machine.log.info("Hardware pins mapped. Beginning 15-second SGP30 warmup...")
            
        except Exception as e:
            machine.flags['error_message'] = f"Hardware Initialization failed: {e}"
            machine.log.critical(machine.flags['error_message'])
            machine.go_to_state('Error')

    def update(self, machine):
        now = time.monotonic()
        # Non-blocking 15-second delay to establish the SGP30 baseline
        if now - self.start_time < 15.0:
            if now - self.last_sgp_read >= 1.0:
                # Discard reading, just ensuring it maintains baseline
                _ = machine.hardware['sgp30'].eCO2
                self.last_sgp_read = now
        else:
            machine.flags['sgp30_ready'] = True
            machine.log.info("Initialization complete. SGP30 warmed up.")
            machine.go_to_state('Idle')


class CustomIdle(GenericIdle):
    """
    Inherits from GenericIdle to maintain telemetry and instruction checking,
    but adds a 1Hz background poll to keep the SGP30 properly calibrated.
    """
    @property
    def name(self): return 'Idle'

    def enter(self, machine, context=None):
        super().enter(machine, context)
        self.last_sgp30_read = time.monotonic()

    def update(self, machine):
        super().update(machine)
        now = time.monotonic()
        
        # Read the SGP30 every 1 second to retain sensor calibration
        if now - self.last_sgp30_read >= 1.0:
            if machine.flags.get('sgp30_ready'):
                try:
                    # Execute read, value discarded unless command requested
                    _ = machine.hardware['sgp30'].eCO2
                    _ = machine.hardware['sgp30'].TVOC
                except Exception as e:
                    machine.log.debug(f"SGP30 Idle read failed: {e}")
            self.last_sgp30_read = now


# ============================================================================
# SEQUENCER STATES
# ============================================================================

class MoveServo(State):
    """
    A unified state for panning or tilting a servo smoothly over time.
    """
    @property
    def name(self): return 'MoveServo'

    def enter(self, machine, context=None):
        super().enter(machine, context)
        self.servo_name = self.local_context.get('servo_name')
        self.target = self.local_context.get('target_angle')
        
        if self.servo_name is None or self.target is None:
            raise ContextError(f"State '{self.name}' requires 'servo_name' and 'target_angle' in step context.")
        
        self.start = machine.flags[f'{self.servo_name}_angle']
        self.speed = machine.config['operational_parameters']['servo_speed']
        self.distance = self.target - self.start
        
        if self.speed > 0:
            self.duration = abs(self.distance) / self.speed
        else:
            self.duration = 0

        self.start_time = time.monotonic()
        
        if self.duration == 0:
            machine.hardware[f'servo_{self.servo_name}'].angle = self.target
            machine.flags[f'{self.servo_name}_angle'] = self.target
            self.task_complete = True

    def update(self, machine):
        super().update(machine)
        if self.task_complete:
            return
            
        elapsed = time.monotonic() - self.start_time
        if elapsed >= self.duration:
            machine.hardware[f'servo_{self.servo_name}'].angle = self.target
            machine.flags[f'{self.servo_name}_angle'] = self.target
            self.task_complete = True
        else:
            current_angle = self.start + (self.distance * (elapsed / self.duration))
            machine.hardware[f'servo_{self.servo_name}'].angle = current_angle
            machine.flags[f'{self.servo_name}_angle'] = current_angle


class PlayTone(State):
    """
    A sequencer state that turns the buzzer on for a non-blocking duration.
    """
    @property
    def name(self): return 'PlayTone'

    def enter(self, machine, context=None):
        super().enter(machine, context)
        frequency = self.local_context.get('frequency')
        self.duration = self.local_context.get('duration')
        
        if frequency is None or self.duration is None:
            raise ContextError(f"State '{self.name}' requires 'frequency' and 'duration' in step context.")
        
        buzzer = machine.hardware['buzzer']
        buzzer.frequency = frequency
        buzzer.duty_cycle = 32768
        self.start_time = time.monotonic()

    def update(self, machine):
        super().update(machine)
        if self.task_complete:
            return
        if time.monotonic() - self.start_time >= self.duration:
            machine.hardware['buzzer'].duty_cycle = 0
            self.task_complete = True