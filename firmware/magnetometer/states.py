# firmware/magnetometer/states.py
# type: ignore
import board
import time
import neopixel
from shared_lib.statemachine import State
import adafruit_tlv493d
import hmc5883
from shared_lib.messages import Message

# ============================================================================
# STATE: Initialize
# ============================================================================
class Initialize(State):
    """Initializes the I2C bus and both magnetometer sensors."""
    @property
    def name(self):
        return 'Initialize'

    def enter(self, machine, context=None):
        super().enter(machine, context)
        try:
            # Initialize I2C bus
            machine.i2c = board.I2C()
            machine.log.info("I2C bus initialized.")

            # Initialize TLV493D sensor
            machine.tlv = adafruit_tlv493d.TLV493D(machine.i2c)
            machine.log.info("TLV493D sensor found and initialized.")

            # Initialize HMC5883 sensor
            machine.hmc = hmc5883.HMC5883(machine.i2c)
            machine.log.info("HMC5883 sensor found and initialized.")

            # Initialize NeoPixel LED
            machine.led = neopixel.NeoPixel(board.NEOPIXEL, 1)
            machine.led.brightness = 1.0  # Full brightness when IDLE
            machine.led.fill((255, 255, 255))
            machine.log.info("NeoPixel initialized.")

            # Initialize offset storage
            machine.tlv_offsets = {'x': 0, 'y': 0, 'z': 0}
            machine.hmc_offsets = {'x': 0, 'y': 0, 'z': 0}

            # Run calibration on startup
            self._calibrate_sensors(machine)

            machine.log.info("Magnetometer initialization complete.")
            machine.go_to_state('Idle')
        except Exception as e:
            machine.flags['error_message'] = f"Failed to initialize magnetometer: {e}"
            machine.log.critical(machine.flags['error_message'])
            machine.go_to_state('Error')

    def _calibrate_sensors(self, machine):
        """Calibrate sensors by taking 10 measurements and calculating offsets."""
        machine.log.info("Calibrating sensors...")

        # Accumulate values for TLV493D
        tlv_x_sum = 0
        tlv_y_sum = 0
        tlv_z_sum = 0

        # Accumulate values for HMC5883
        hmc_x_sum = 0
        hmc_y_sum = 0
        hmc_z_sum = 0

        # Take 10 measurements
        for i in range(10):
            # Read TLV493D
            tlv_raw_x, tlv_raw_y, tlv_raw_z = machine.tlv.magnetic
            tlv_x_sum += tlv_raw_x
            tlv_y_sum += tlv_raw_y
            tlv_z_sum += tlv_raw_z

            # Read HMC5883
            hmc_raw_x, hmc_raw_y, hmc_raw_z = machine.hmc.magnetic
            hmc_x_sum += hmc_raw_x
            hmc_y_sum += hmc_raw_y
            hmc_z_sum += hmc_raw_z

            # Small delay between measurements
            time.sleep(0.05)

        # Calculate average offsets
        machine.tlv_offsets['x'] = tlv_x_sum / 10
        machine.tlv_offsets['y'] = tlv_y_sum / 10
        machine.tlv_offsets['z'] = tlv_z_sum / 10

        machine.hmc_offsets['x'] = hmc_x_sum / 10
        machine.hmc_offsets['y'] = hmc_y_sum / 10
        machine.hmc_offsets['z'] = hmc_z_sum / 10

        machine.log.info("Calibration complete:")
        machine.log.info(f"TLV493D offsets: X={machine.tlv_offsets['x']:.2f}, Y={machine.tlv_offsets['y']:.2f}, Z={machine.tlv_offsets['z']:.2f} uT")
        machine.log.info(f"HMC5883 offsets: X={machine.hmc_offsets['x']:.2f}, Y={machine.hmc_offsets['y']:.2f}, Z={machine.hmc_offsets['z']:.2f} Gs")

    def update(self, machine):
        """Handle state updates - immediate transition on enter."""
        super().update(machine)


# ============================================================================
# STATE: Zeroing
# ============================================================================
class Zeroing(State):
    """Calibrates sensors by averaging 10 readings from each sensor."""
    @property
    def name(self):
        return 'Zeroing'

    def enter(self, machine, context=None):
        super().enter(machine, context)

        # Initialize progress tracking
        machine.flags['zero_progress'] = 0
        machine.flags['zero_complete'] = False

        # Blink NeoPixel during calibration (medium brightness)
        #machine.led.brightness = 0.5
        machine.led.fill((127, 127, 127))
        machine.log.info("Starting calibration...")

        # Accumulate values for TLV493D
        tlv_x_sum = 0
        tlv_y_sum = 0
        tlv_z_sum = 0

        # Accumulate values for HMC5883
        hmc_x_sum = 0
        hmc_y_sum = 0
        hmc_z_sum = 0

        # Take 10 measurements from each sensor
        for i in range(10):
            # Read TLV493D
            tlv_raw_x, tlv_raw_y, tlv_raw_z = machine.tlv.magnetic
            tlv_x_sum += tlv_raw_x
            tlv_y_sum += tlv_raw_y
            tlv_z_sum += tlv_raw_z

            # Read HMC5883
            hmc_raw_x, hmc_raw_y, hmc_raw_z = machine.hmc.magnetic
            hmc_x_sum += hmc_raw_x
            hmc_y_sum += hmc_raw_y
            hmc_z_sum += hmc_raw_z

            # Update progress
            machine.flags['zero_progress'] = i + 1

            # Small delay between measurements
            time.sleep(0.05)

        # Calculate average offsets
        machine.tlv_offsets['x'] = tlv_x_sum / 10
        machine.tlv_offsets['y'] = tlv_y_sum / 10
        machine.tlv_offsets['z'] = tlv_z_sum / 10

        machine.hmc_offsets['x'] = hmc_x_sum / 10
        machine.hmc_offsets['y'] = hmc_y_sum / 10
        machine.hmc_offsets['z'] = hmc_z_sum / 10

        machine.log.info("Calibration complete:")
        machine.log.info(f"TLV493D offsets: X={machine.tlv_offsets['x']:.2f}, Y={machine.tlv_offsets['y']:.2f}, Z={machine.tlv_offsets['z']:.2f} uT")
        machine.log.info(f"HMC5883 offsets: X={machine.hmc_offsets['x']:.2f}, Y={machine.hmc_offsets['y']:.2f}, Z={machine.hmc_offsets['z']:.2f} Gs")

        machine.flags['zero_progress'] = 10
        machine.flags['zero_complete'] = True

        # Turn NeoPixel back to full brightness (IDLE state)
        #machine.led.brightness = 1.0
        machine.led.fill((255, 255, 255))

        machine.log.info("Zeroing complete. Transitioning to Idle.")
        machine.go_to_state('Idle')

    def update(self, machine):
        """Handle state updates - immediate transition on enter."""
        super().update(machine)