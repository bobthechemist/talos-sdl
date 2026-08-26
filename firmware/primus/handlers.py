# firmware/primus/handlers.py
#type: ignore
from shared_lib.messages import send_problem, send_success, Message
from shared_lib.error_handling import try_wrapper
import adafruit_as7341  # Required for mapping gain constants

# ----------------------------------------------------------------------------
# HARDWARE HANDLERS
# ----------------------------------------------------------------------------
@try_wrapper
def handle_pan(machine, payload):
    args = payload.get("args", {})
    angle = args.get("angle")
    if angle is None or not isinstance(angle, (int, float)):
        send_problem(machine, "Valid 'angle' argument is required.")
        return
    if not (0 <= angle <= 180):
        send_problem(machine, "Pan angle must be between 0 and 180 degrees.")
        return
    sequence = [{"state": "MoveServo", "label": f"Panning to {angle} degrees", "context": {"servo_name": "pan", "target_angle": float(angle)}}]
    machine.sequencer.start(sequence, initial_context={'name': 'pan'})

@try_wrapper
def handle_tilt(machine, payload):
    args = payload.get("args", {})
    angle = args.get("angle")
    if angle is None or not isinstance(angle, (int, float)):
        send_problem(machine, "Valid 'angle' argument is required.")
        return
    if not (0 <= angle <= 180):
        send_problem(machine, "Tilt angle must be between 0 and 180 degrees.")
        return
    sequence = [{"state": "MoveServo", "label": f"Tilting to {angle} degrees", "context": {"servo_name": "tilt", "target_angle": float(angle)}}]
    machine.sequencer.start(sequence, initial_context={'name': 'tilt'})

@try_wrapper
def handle_light(machine, payload):
    args = payload.get("args", {})
    color = args.get("color")
    pixel = args.get("pixel")
    if pixel not in [0, 1]:
        send_problem(machine, "Pixel index must be 0 or 1.")
        return
    if not isinstance(color, list) or len(color) != 3:
        send_problem(machine, "Color must be a 3-element list of integers.")
        return
    try:
        color_tuple = (int(color[0]), int(color[1]), int(color[2]))
        if not all(0 <= val <= 255 for val in color_tuple):
            send_problem(machine, "Color values must be between 0 and 255.")
            return
        machine.hardware['pixels'][pixel] = color_tuple
        machine.flags[f'pixel_{pixel}_color'] = color
        send_success(machine, f"Pixel {pixel} updated successfully.")
    except ValueError:
        send_problem(machine, "Color array must contain valid integers.")

@try_wrapper
def handle_play(machine, payload):
    args = payload.get("args", {})
    freq = args.get("frequency")
    duration = args.get("duration")
    if not isinstance(freq, (int, float)) or not isinstance(duration, (int, float)):
        send_problem(machine, "Both 'frequency' and 'duration' must be provided as numbers.")
        return
    if freq < 20 or freq > 20000:
        send_problem(machine, "Frequency out of audible range.")
        return
    sequence = [{"state": "PlayTone", "label": f"Playing {freq}Hz for {duration}s", "context": {"frequency": int(freq), "duration": float(duration)}}]
    machine.sequencer.start(sequence, initial_context={'name': 'play tone'})

# ----------------------------------------------------------------------------
# SENSOR HANDLERS (SGP30, VL53L0X, AS7341)
# ----------------------------------------------------------------------------

@try_wrapper
def handle_read_ec02(machine, payload):
    if not machine.flags.get('sgp30_ready'):
        send_problem(machine, "SGP30 is still initializing (requires 15s warmup).")
        return
    eco2_val = machine.hardware['sgp30'].eCO2
    response = Message(subsystem_name=machine.name, status="DATA_RESPONSE", payload={"data": {"eCO2_ppm": eco2_val}})
    machine.postman.send(response.serialize())

@try_wrapper
def handle_read_voc(machine, payload):
    if not machine.flags.get('sgp30_ready'):
        send_problem(machine, "SGP30 is still initializing (requires 15s warmup).")
        return
    tvoc_val = machine.hardware['sgp30'].TVOC
    response = Message(subsystem_name=machine.name, status="DATA_RESPONSE", payload={"data": {"TVOC_ppb": tvoc_val}})
    machine.postman.send(response.serialize())

@try_wrapper
def handle_read_distance(machine, payload):
    val_mm = machine.hardware['vl53l0x'].range
    val_cm = val_mm / 10.0
    response = Message(subsystem_name=machine.name, status="DATA_RESPONSE", payload={"data": {"distance_cm": val_cm}})
    machine.postman.send(response.serialize())

@try_wrapper
def handle_read_all(machine, payload):
    channels = machine.hardware['as7341'].all_channels
    # Returns a tuple of 6 values: [F1, F2, F3, F4, Clear, NIR] depending on mux step
    response = Message(subsystem_name=machine.name, status="DATA_RESPONSE", payload={"data": {"spectral_channels": list(channels)}})
    machine.postman.send(response.serialize())

@try_wrapper
def handle_set_gain(machine, payload):
    args = payload.get("args", {})
    multiplier = args.get("multiplier")
    
    # Map raw multiplier to adafruit_as7341 constants
    gain_map = {
        0.5: adafruit_as7341.Gain.GAIN_0_5X,
        1: adafruit_as7341.Gain.GAIN_1X,
        2: adafruit_as7341.Gain.GAIN_2X,
        4: adafruit_as7341.Gain.GAIN_4X,
        8: adafruit_as7341.Gain.GAIN_8X,
        16: adafruit_as7341.Gain.GAIN_16X,
        32: adafruit_as7341.Gain.GAIN_32X,
        64: adafruit_as7341.Gain.GAIN_64X,
        128: adafruit_as7341.Gain.GAIN_128X,
        256: adafruit_as7341.Gain.GAIN_256X,
        512: adafruit_as7341.Gain.GAIN_512X
    }
    
    if multiplier not in gain_map:
        send_problem(machine, f"Invalid multiplier. Allowed: {list(gain_map.keys())}")
        return
        
    machine.hardware['as7341'].gain = gain_map[multiplier]
    send_success(machine, f"AS7341 gain set to {multiplier}X")

@try_wrapper
def handle_set_source(machine, payload):
    args = payload.get("args", {})
    intensity = args.get("intensity")
    
    if intensity is None or not isinstance(intensity, (int, float)):
        send_problem(machine, "Intensity must be a valid number.")
        return
        
    if not (0 <= intensity <= 10):
        send_problem(machine, "Intensity must be between 0 and 10 mA.")
        return
        
    machine.hardware['as7341'].led_current = float(intensity)
    send_success(machine, f"AS7341 LED intensity set to {intensity} mA")

@try_wrapper
def handle_source_on(machine, payload):
    machine.hardware['as7341'].led = True
    send_success(machine, "AS7341 LED source turned ON")

@try_wrapper
def handle_source_off(machine, payload):
    machine.hardware['as7341'].led = False
    send_success(machine, "AS7341 LED source turned OFF")