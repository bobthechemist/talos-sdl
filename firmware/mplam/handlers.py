# firmware/mplam/handlers.py
# type: ignore
import time
from shared_lib.messages import Message, send_problem, send_success
from shared_lib.error_handling import try_wrapper

@try_wrapper
def handle_set_neopixel(machine, payload):
    """Sets the color and brightness of a single NeoPixel."""
    args = payload.get("args", {})
    pixel_id = args.get("pixel")
    color = args.get("color")
    brightness = args.get("brightness")

    # --- Guard Conditions ---
    if not isinstance(pixel_id, int) or not (0 <= pixel_id < machine.config["neopixel_count"]):
        send_problem(machine, f"Invalid pixel ID. Must be an integer between 0 and {machine.config['neopixel_count'] - 1}.")
        return
    if not isinstance(color, list) or len(color) != 3 or not all(isinstance(c, int) and 0 <= c <= 255 for c in color):
        send_problem(machine, "Invalid color. Must be a list of 3 integers [R, G, B] between 0 and 255.")
        return

    # --- Actions ---
    machine.pixels[pixel_id] = tuple(color)

    if brightness is not None:
        max_b = machine.config["max_brightness"]
        if isinstance(brightness, (float, int)) and 0.0 <= brightness <= max_b:
            machine.pixels.brightness = float(brightness)
        else:
            send_problem(machine, f"Invalid brightness. Must be a float between 0.0 and {max_b}.")
            return
            
    machine.pixels.show()
    send_success(machine, f"Set NeoPixel {pixel_id} to {color} with brightness {machine.pixels.brightness:.2f}.")

@try_wrapper
def handle_set_status(machine, payload):
    """Turns a single blue status LED on or off."""
    args = payload.get("args", {})
    led_id = args.get("led")
    value = args.get("value")

    # --- Guard Conditions ---
    if not isinstance(led_id, int) or not (1 <= led_id <= len(machine.status_leds)):
        send_problem(machine, f"Invalid LED number. Must be an integer between 1 and {len(machine.status_leds)}.")
        return
    if not isinstance(value, bool):
        send_problem(machine, "Invalid value. Must be a boolean (true or false).")
        return

    # --- Action ---
    machine.status_leds[led_id - 1].value = value
    send_success(machine, f"Set status LED {led_id} to {'ON' if value else 'OFF'}.")

@try_wrapper
def handle_get_status(machine, payload):
    """
    Returns the on/off state of one or all status LEDs.
    REVISED: Always returns a list of boolean(s) in the data payload.
    """
    args = payload.get("args", {})
    led_id = args.get("led")
    
    status_data = {}

    if led_id is not None:
        # Get status of a single LED
        if not isinstance(led_id, int) or not (1 <= led_id <= len(machine.status_leds)):
            send_problem(machine, f"Invalid LED number. Must be an integer between 1 and {len(machine.status_leds)}.")
            return
        # REVISED: Return value is a list containing one boolean
        status_data = {"led_states": [machine.status_leds[led_id - 1].value]}
    else:
        # Get status of all LEDs
        status_data = {"led_states": [led.value for led in machine.status_leds]}

    response = Message.create_message(
        subsystem_name=machine.name,
        status="DATA_RESPONSE",
        payload={
            "metadata": {"data_type": "led_status_list"},
            "data": status_data
        }
    )
    machine.postman.send(response.serialize())


@try_wrapper
def handle_clear_all(machine, payload):
    """Turns off all indicators."""
    for led in machine.status_leds:
        led.value = False
    machine.pixels.fill((0, 0, 0))
    machine.pixels.show()
    machine.buzzer.duty_cycle = 0
    send_success(machine, "All indicators cleared.")

@try_wrapper
def handle_set_buzzer(machine, payload):
    """Starts a non-blocking buzzer sequence."""
    args = payload.get("args", {})
    frequency = args.get("frequency")
    duration = args.get("duration")

    # --- Guard Conditions ---
    if not isinstance(frequency, int) or not (20 <= frequency <= 20000):
        send_problem(machine, "Invalid frequency. Must be an integer between 20 and 20000.")
        return
    if not isinstance(duration, (float, int)) or not (0 < duration <= 2.0):
        send_problem(machine, "Invalid duration. Must be a float between 0.0 and 2.0.")
        return
    
    # --- Start Sequencer ---
    sequence = [{"state": "BuzzerActive"}]
    context = {
        "name": "set_buzzer",
        "frequency": frequency,
        "duration": float(duration)
    }
    machine.sequencer.start(sequence, initial_context=context)