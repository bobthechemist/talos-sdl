# firmware/colorimeter/states.py
# REFACTORED: Fixed all 'enter' method signatures to be compatible with the base class.
# type: ignore
import board
import time
from shared_lib.statemachine import State
import adafruit_as7341
from .handlers import CHANNEL_NAMES
from shared_lib.messages import Message

class Initialize(State):
    """Initializes the I2C bus and the AS7341 sensor."""
    @property
    def name(self): return 'Initialize'

    def enter(self, machine, context=None):
        super().enter(machine, context)
        try:
            i2c = board.I2C()
            machine.sensor = adafruit_as7341.AS7341(i2c)
            machine.log.info("AS7341 sensor found and initialized.")

            default_gain_val = machine.config.get("default_gain", 8)
            default_intensity = machine.config.get("default_intensity", 4)
            
            from .handlers import VALID_GAINS
            machine.sensor.gain = VALID_GAINS.index(default_gain_val)
            machine.sensor.led_current = default_intensity
            machine.sensor.led = False

            machine.log.info(f"Default settings: Gain={default_gain_val}x, Intensity={default_intensity}mA")
            machine.go_to_state('Idle')
        except Exception as e:
            machine.flags['error_message'] = f"Failed to initialize AS7341 sensor: {e}"
            machine.log.critical(machine.flags['error_message'])
            machine.go_to_state('Error')

# ============================================================================
# STATES FOR THE 'measure' COMMAND SEQUENCE
# ============================================================================

class TurnOnLED(State):
    """Sequencer State: Turns the LED on and waits briefly for it to stabilize."""
    @property
    def name(self): return 'TurnOnLED'

    # <<< FIX IS HERE: Method signature now accepts context.
    def enter(self, machine, context=None):
        super().enter(machine, context)
        machine.sensor.led = True
        time.sleep(0.2)
        self.task_complete = True # Signal to base class that this state is done.

    def update(self, machine):
        super().update(machine) # Base class handles sequencer advancement now.

class ReadSensor(State):
    """Sequencer State: Reads the sensor and stores the result in the sequencer's context."""
    @property
    def name(self): return 'ReadSensor'

    # <<< FIX IS HERE: Method signature now accepts context.
    def enter(self, machine, context=None):
        super().enter(machine, context)
        machine.sequencer.context['raw_readings'] = machine.sensor.all_channels
        machine.log.info("Sensor readings acquired.")
        self.task_complete = True

    def update(self, machine):
        super().update(machine)

class TurnOffLED(State):
    """Sequencer State: Turns LED off, formats data, and sends the final response."""
    @property
    def name(self): return 'TurnOffLED'

    # <<< FIX IS HERE: Method signature now accepts context.
    def enter(self, machine, context=None):
        super().enter(machine, context)
        machine.sensor.led = False
        
        readings_tuple = machine.sequencer.context.get('raw_readings')
        
        if readings_tuple:
            readings_dict = dict(zip(CHANNEL_NAMES, readings_tuple))
            response = Message.create_message(
                subsystem_name=machine.name,
                status="DATA_RESPONSE",
                payload={
                    "metadata": { "data_type": "color_spectrum", "units": "counts" },
                    "data": readings_dict
                }
            )
            machine.postman.send(response.serialize())
        else:
            from shared_lib.messages import send_problem
            send_problem(machine, "Measurement failed: could not retrieve sensor data from context.")

        self.task_complete = True

    def update(self, machine):
        super().update(machine)