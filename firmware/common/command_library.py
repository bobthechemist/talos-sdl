# shared_lib/command_library.py
#type: ignore
from shared_lib.messages import Message, send_problem, send_success
import time

# Helper function, not a class, to register common commands.
def register_common_commands(machine):
    """
    Inspects this module and registers all common commands
    with the provided state machine instance.
    """
    # In a real implementation, you would introspect or just explicitly define.
    # For clarity, we will be explicit here.
    
    machine.add_command("help", handle_help, {
        "description": "Returns a list of all supported commands.",
        "args": []
    })
    machine.add_command("ping", handle_ping, {
        "description": "Responds with 'pong' to check connectivity.",
        "args": []
    })
    machine.add_command("set_time", handle_set_time, {
        "description": "Sets the time of the microcontroller.",
        "args": ["epoch_seconds: int"],
        "args": [
            {"name": "epoch_seconds", "type": "int", "description": "output of time.time()"}
        ]
    })
    machine.add_command("get_info", handle_get_info, {
        "description": "Retrieves status information.",
        "args": []
    })
    machine.add_command("enable_continuous", handle_enable_continuous, {
        "description": "Enable continuous mode for live view.",
        "args": []
    })
    machine.add_command("read_continuous", handle_read_continuous, {
        "description": "Reads sensor continuously for live view.",
        "args": ["rate: int"]
    })

# --- Handler functions are now standalone ---
def handle_help(machine, payload):
    """Sends the machine's fully assembled list of supported commands."""
    machine.log.info("Help command received. Sending capabilities.")
    response = Message(
        subsystem_name=machine.name,
        status="DATA_RESPONSE",
        payload={
            "metadata": {
                "data_type": "dict",
                "ai_guidance": machine.config.get("ai_guidance", "")
            },
            "data": machine.supported_commands # Get it directly from the machine
        }
    )
    machine.postman.send(response.serialize())

def handle_ping(machine, payload):
    """Responds with a simple 'pong'."""
    send_success(machine, "pong")

def handle_set_time(machine, payload):
    """
    Sets the device's real-time clock (RTC) based on the epoch seconds 
    provided by the host.

    Args:
        machine: The main device state object (contains 'name', 'log', etc.).
        payload: The payload dictionary from the INSTRUCTION message.
    """
    try:
        # 1. Safely get the arguments from the payload
        args = payload.get("args", {})
        epoch_seconds = args.get("epoch_seconds")
        tz_offset = machine.config.get("timezone",14400) # This is a hack, needs updating

        #TODO: Figure out how to grab this information from the timestamp, which is presently not accessible to handlers
        if epoch_seconds is None or not isinstance(epoch_seconds, (int, float)):
            machine.log.info("Incorrect or missing argument in set_time.")


        # 2. Import rtc and perform the logic
        import rtc  # Local import is memory efficient
        
        # The RTC object is a singleton, get the instance
        the_rtc = rtc.RTC()
        
        # Convert epoch seconds to a time.struct_time, which the RTC requires
        new_time = time.localtime(epoch_seconds - tz_offset)
        
        # Set the RTC datetime
        the_rtc.datetime = new_time
        

        # 3. Log the success and create a success response message
        # You can format the time nicely for the log
        formatted_time = f"{new_time.tm_year}-{new_time.tm_mon:02d}-{new_time.tm_mday:02d} {new_time.tm_hour:02d}:{new_time.tm_min:02d}:{new_time.tm_sec:02d}"
        send_success(machine, f"Local time set to: {formatted_time}")

    except Exception as e:
        # 4. If anything goes wrong, create a PROBLEM response
        send_problem(machine, "Failed to set local time", str(e))


def handle_get_info(machine, payload):
    """
    Handles the 'get_info' command. It assembles a standardized status
    report by accessing core machine attributes and calling the machine's
    registered status_callback function to get instrument-specific data.
    """
    try:
        # 1. Assemble the payload from the standard, guaranteed attributes.
        info_payload = {
            "metadata":{
                "firmware_name": machine.name,
                "firmware_version": machine.version,
                "current_state": machine.state.name,
                "data_type": "dict"
            },

            # 2. Call the machine's registered callback function to compute
            #    the instrument-specific status dictionary in real-time.
            "data": machine.build_status_info(machine)
        }

        # 3. Create the SUCCESS message with the assembled payload.
        response = Message.create_message(
            subsystem_name=machine.name,
            status="DATA_RESPONSE",
            payload=info_payload
        )
        machine.postman.send(response.serialize())
    except Exception as e:
        send_problem(machine, "Failed to retrieve device info", str(e))

def handle_enable_continuous(machine, payload):
    """
    Enables continuous mode for the magnetometer device.
    Sets a flag that allows the read_continuous command to run without
    requiring manual enable each time.
    """
    try:
        machine.flags['continuous_mode'] = True
        machine.flags['sample_counter'] = 0
        send_success(machine, "Continuous mode enabled")
    except Exception as e:
        send_problem(machine, f"Failed to enable continuous mode: {e}")

def handle_read_continuous(machine, payload):
    """
    Handles the 'read_continuous' command.
    Reads sensor and returns data with timestamp and sample number.

    Args:
        machine: The main device state object
        payload: The payload dictionary with rate parameter

    Returns:
        DATA_RESPONSE message with magnetic field data
    """
    try:
        # Get arguments
        args = payload.get("args", {})
        rate = args.get("rate", 5)  # Default 5 Hz

        # Check if machine has continuous mode enabled
        if not machine.flags.get('continuous_mode', False):
            send_problem(machine, "Continuous mode not enabled. Use enable_continuous first.")
            return

        # Enable internal counter
        if 'sample_counter' not in machine.flags:
            machine.flags['sample_counter'] = 0
        machine.flags['sample_counter'] += 1

        # Read sensors
        if hasattr(machine, 'tlv') and hasattr(machine.hmc):
            # Magnetometer device
            tlv_raw_x, tlv_raw_y, tlv_raw_z = machine.tlv.magnetic
            hmc_raw_x, hmc_raw_y, hmc_raw_z = machine.hmc.magnetic

            # Apply offsets if available
            tlv_corrected = {
                'x': tlv_raw_x - machine.tlv_offsets.get('x', 0),
                'y': tlv_raw_y - machine.tlv_offsets.get('y', 0),
                'z': tlv_raw_z - machine.tlv_offsets.get('z', 0)
            }

            hmc_corrected = {
                'x': hmc_raw_x - machine.hmc_offsets.get('x', 0),
                'y': hmc_raw_y - machine.hmc_offsets.get('y', 0),
                'z': hmc_raw_z - machine.hmc_offsets.get('z', 0)
            }
        else:
            send_problem(machine, "No magnetometer sensors available")
            return

        # Create response
        response = Message.create_message(
            subsystem_name=machine.name,
            status="DATA_RESPONSE",
            payload={
                "metadata": {
                    "data_type": "magnetic_field_continuous",
                    "units": "mixed",
                    "timestamp": time.time(),
                    "sample_number": machine.flags['sample_counter']
                },
                "data": {
                    "tlv493d": tlv_corrected,
                    "hmc5883": hmc_corrected
                }
            }
        )
        machine.postman.send(response.serialize())

    except Exception as e:
        send_problem(machine, f"Error in read_continuous: {e}")

