# firmware/mplam/states.py
# type: ignore
import board
import time
import digitalio
import neopixel
import pwmio
from shared_lib.statemachine import State

class Initialize(State):
    """
    Initializes all hardware components for the MPLAM.
    REVISED: Includes a blocking 'Lamp Test' sequence on successful init.
    """
    @property
    def name(self):
        return 'Initialize'

    def enter(self, machine, context=None):
        super().enter(machine, context)
        try:
            # 1. Initialize Blue Status LEDs
            machine.status_leds = []
            for pin in machine.config["pins"]["blue_leds"]:
                led = digitalio.DigitalInOut(pin)
                led.direction = digitalio.Direction.OUTPUT
                led.value = False
                machine.status_leds.append(led)
            machine.log.info(f"Initialized {len(machine.status_leds)} status LEDs.")

            # 2. Initialize NeoPixels
            pin = machine.config["pins"]["neopixel_pin"]
            count = machine.config["neopixel_count"]
            brightness = machine.config["default_brightness"]
            machine.pixels = neopixel.NeoPixel(pin, count, brightness=brightness, auto_write=False)
            machine.pixels.fill((0, 0, 0))
            machine.pixels.show()
            machine.log.info(f"Initialized {count} NeoPixels on {str(pin)}.")

            # 3. Initialize Buzzer
            buzzer_pin = machine.config["pins"]["buzzer"]
            machine.buzzer = pwmio.PWMOut(buzzer_pin, variable_frequency=True, duty_cycle=0)
            machine.log.info(f"Initialized buzzer PWM on {str(buzzer_pin)}.")
            
            # 4. Initialize Buttons (as inputs)
            machine.button1 = digitalio.DigitalInOut(machine.config["pins"]["button_1"])
            machine.button1.direction = digitalio.Direction.INPUT
            machine.button1.pull = digitalio.Pull.UP
            machine.button2 = digitalio.DigitalInOut(machine.config["pins"]["button_2"])
            machine.button2.direction = digitalio.Direction.INPUT
            machine.button2.pull = digitalio.Pull.UP
            machine.log.info("Initialized buttons.")

            # --- REVISED: Perform blocking Lamp Test ---
            machine.log.info("Performing blocking lamp test...")
            # Cycle NeoPixels
            colors = [(25, 0, 0), (0, 25, 0), (0, 0, 25)]
            for color in colors:
                machine.pixels.fill(color)
                machine.pixels.show()
                time.sleep(0.1)
            machine.pixels.fill((0, 0, 0))
            machine.pixels.show()
            # "Knight Rider" scan on blue LEDs
            for i in range(len(machine.status_leds)):
                machine.status_leds[i].value = True
                time.sleep(0.02)
                machine.status_leds[i].value = False
            for i in range(len(machine.status_leds) - 1, -1, -1):
                machine.status_leds[i].value = True
                time.sleep(0.02)
                machine.status_leds[i].value = False
            machine.log.info("Lamp test complete.")

            # If all successful, transition to Idle
            machine.go_to_state('Idle')

        except Exception as e:
            machine.flags['error_message'] = f"Hardware Initialization failed: {e}"
            machine.log.critical(machine.flags['error_message'])
            machine.go_to_state('Error')

class BuzzerActive(State):
    """
    A temporary, non-blocking state to manage the buzzer duration.
    This state is controlled by the StateSequencer.
    """
    @property
    def name(self):
        return 'BuzzerActive'
    
    def enter(self, machine, context=None):
        super().enter(machine, context)
        self.required_context = ["frequency", "duration"]
        self._validate_context(machine, context)
        
        frequency = machine.sequencer.context["frequency"]
        duration = machine.sequencer.context["duration"]
        
        # Start the buzzer
        machine.buzzer.frequency = frequency
        machine.buzzer.duty_cycle = 2**15  # 50% duty cycle
        
        # Set the end time
        self.end_time = time.monotonic() + duration
        machine.log.info(f"Buzzer active at {frequency}Hz for {duration}s.")
        
    def update(self, machine):
        # This state doesn't need to call the base update because it manages its own completion.
        if time.monotonic() >= self.end_time:
            # Time's up, turn off the buzzer and signal completion
            machine.buzzer.duty_cycle = 0
            self.task_complete = True
            machine.log.info("Buzzer sequence finished.")
        # We must call the sequencer advance logic at the end.
        super().update(machine)
        
    def exit(self, machine):
        # Safety measure: ensure the buzzer is always off when leaving the state
        machine.buzzer.duty_cycle = 0
        super().exit(machine)