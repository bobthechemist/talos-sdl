# host/ai/ai_utils.py
import sys
import time
import queue
import re
import json
from pathlib import Path

# Setup project root path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from host.core.device_manager import DeviceManager
from host.core.discovery import find_data_comports
from host.firmware_db import get_device_name
from host.gui.console import C
from shared_lib.messages import Message

def world_building():
    """
    Conducts an interactive user interview to build the initial "world model"
    for the AI to operate within, including save/load functionality.
    """
    world_model = {}
    
    print("\n" + "="*60)
    print(" " * 16 + f"{C.INFO}AI Host: World Model Setup{C.END}" + " " * 17)
    print("="*60)
    print("Please answer the following questions to set up the experiment.")

    # --- 1. Reagent Mapping ---
    print(f"\n{C.WARN}[1] Reagent Configuration{C.END}")
    reagent_map = {}
    for i in range(1, 5):
        pump_id = f"p{i}"
        reagent_name = input(f"  -> What liquid is in pump {pump_id}? (Press Enter to skip): ").strip()
        if reagent_name:
            reagent_map[pump_id] = reagent_name
    world_model['reagents'] = reagent_map
    print(f"{C.OK}  Reagents mapped: {world_model['reagents']}{C.END}")

    # --- 2. Well Plate State ---
    print(f"\n{C.WARN}[2] Well Plate State{C.END}")
    while True:
        resp = input("  -> Can I assume the 96-well plate is completely empty? [y/n]: ").strip().lower()
        if resp in ('y', 'yes'):
            world_model['plate_is_empty'] = True
            break
        elif resp in ('n', 'no'):
            print(f"{C.ERR}  This script currently only supports starting with an empty plate. Aborting.{C.END}")
            return None 
        else:
            print(f"{C.ERR}  Invalid response. Please enter 'y' or 'n'.{C.END}")

    # --- 3. Maximum Well Volume ---
    print(f"\n{C.WARN}[3] Well Plate Parameters{C.END}")
    while True:
        try:
            max_vol = float(input("  -> What is the maximum safe volume for a single well (in µL)?: ").strip())
            if max_vol > 0:
                world_model['max_well_volume_ul'] = max_vol
                break
            else:
                print(f"{C.ERR}  Volume must be a positive number.{C.END}")
        except ValueError:
            print(f"{C.ERR}  Invalid input. Please enter a number.{C.END}")

    # --- 4. Standard Dispense Volume ---
    while True:
        try:
            std_vol = float(input(f"  -> What is the standard volume to dispense for tasks (in µL)?: ").strip())
            if std_vol <= 0:
                print(f"{C.ERR}  Volume must be a positive number.{C.END}")
            elif std_vol > world_model['max_well_volume_ul']:
                print(f"{C.ERR}  Standard volume cannot exceed the maximum volume ({world_model['max_well_volume_ul']} µL).{C.END}")
            else:
                world_model['standard_dispense_ul'] = std_vol
                break
        except ValueError:
            print(f"{C.ERR}  Invalid input. Please enter a number.{C.END}")
            
    # --- 7. Experiment Name ---
    print(f"\n{C.WARN}[4] Data Logging{C.END}")
    while True:
        exp_name = input("  -> What is the name for this experiment (for the output file)?: ").strip()
        sanitized_name = re.sub(r'[^\w\-_.]', '_', exp_name)
        if sanitized_name:
            world_model['experiment_name'] = sanitized_name
            print(f"{C.OK}  Data will be saved to '{sanitized_name}.csv'{C.END}")
            break
        else:
            print(f"{C.ERR}  Experiment name cannot be empty.{C.END}")

    # --- 8. Waste Location ---
    print(f"\n{C.WARN}[5] Waste Location{C.END}")
    waste_loc = input("  -> Where is the waste location? (e.g., 'A12' or '4.5, -5'): ").strip()
    world_model['waste_location'] = waste_loc

    # --- NEW: Save World Model ---
    while True:
        save_resp = input(f"\n{C.WARN}Would you like to save this world configuration for future use? [y/n]: {C.END}").strip().lower()
        if save_resp in ('y', 'yes'):
            filename = f"{world_model['experiment_name']}_world.json"
            try:
                with open(filename, 'w') as f:
                    json.dump(world_model, f, indent=4)
                print(f"{C.OK}  -> World model saved successfully to '{filename}'.{C.END}")
            except Exception as e:
                print(f"{C.ERR}  -> Error saving file: {e}{C.END}")
            break
        elif save_resp in ('n', 'no'):
            break
        else:
            print(f"{C.ERR}  Invalid response. Please enter 'y' or 'n'.{C.END}")

    print("\n" + "="*60)
    print(f"{C.OK}World model setup complete! The AI will operate with this configuration.{C.END}")
    print("="*60)
    
    return world_model


def load_world_from_file(filepath: str):
    """Loads a world model from a specified JSON file."""
    print(f"\n{C.INFO}[+] Loading world model from '{filepath}'...{C.END}")
    try:
        with open(filepath, 'r') as f:
            world_model = json.load(f)
        print(f"{C.OK}  -> World model loaded successfully.{C.END}")
        return world_model
    except Exception as e:
        print(f"{C.ERR}  -> Error loading world file: {e}{C.END}")
        return None

def connect_devices():
    """
    Decoupled Connection Logic:
    Scans for and connects to ANY recognized Talos devices found in firmware_db.py.
    Automatically generates logical slugs for the AI (e.g., 'Maker Pi' -> 'maker_pi').
    
    Returns:
        tuple: (DeviceManager, dict of {device_slug: port})
    """
    print(f"\n{C.INFO}[+] Scanning for recognized Talos instruments...{C.END}")
    manager = DeviceManager()
    manager.start()

    device_ports_map = {}
    all_ports = find_data_comports()

    if not all_ports:
        print(f"{C.WARN}  -> No CircuitPython devices detected.{C.END}")
        return manager, {}

    for port_info in all_ports:
        port, vid, pid = port_info['port'], port_info['VID'], port_info['PID']
        friendly_name = get_device_name(vid, pid)
        
        # If the device is recognized in our firmware database
        if "Unknown" not in friendly_name:
            # Create a slug/key for the AI (e.g., "Maker Pi Alert Module (Cytron)" -> "maker_pi_alert_module")
            # We strip the manufacturer info in parentheses and convert to snake_case
            clean_name = friendly_name.split('(')[0].strip()
            device_key = clean_name.lower().replace(" ", "_")
            
            print(f"  -> Connecting to {C.OK}{friendly_name}{C.END} on {port}...")
            if manager.connect_device(port, vid, pid):
                device_ports_map[device_key] = port
            else:
                print(f"{C.ERR}     Failed to connect to {port}{C.END}")
    
    if not device_ports_map:
        print(f"{C.WARN}  -> No recognized devices connected. AI will run in simulation mode.{C.END}")
    else:
        print(f"{C.OK}[SUCCESS] Connected to: {list(device_ports_map.keys())}{C.END}")
        
    return manager, device_ports_map

def get_instructions(manager: DeviceManager, device_ports: dict, timeout: int = 5):
    """
    Generic Capability Discovery:
    Sends 'help' commands to all connected devices and returns the FULL 
    payload (including metadata/guidance) for each device.
    """
    if not device_ports:
        return {}

    print(f"\n{C.INFO}[+] Retrieving capabilities from {len(device_ports)} device(s)...{C.END}")
    help_payload = {"func": "help", "args": {}}
    help_message = Message.create_message("AI_HOST", "INSTRUCTION", payload=help_payload)

    for device, port in device_ports.items():
        manager.send_message(port, help_message)

    all_responses = {}
    start_time = time.time()

    # Wait until all devices respond or we hit the timeout
    while len(all_responses) < len(device_ports) and time.time() - start_time < timeout:
        try:
            msg_type, port, msg_data = manager.incoming_message_queue.get_nowait()
            #print(f"[DEBUG] get_instructions consuming: msg_type={msg_type}, port={port}, status={msg_data.status}")

            if msg_type == 'RECV' and msg_data.status == "DATA_RESPONSE":
                # Match the port back to the device slug
                for name, p in device_ports.items():
                    if p == port and name not in all_responses:
                        #print(f"[DEBUG]   Received response for {name} on {port}")
                        #print(f"[DEBUG]     Status: {msg_data.status}")
                        #print(f"[DEBUG]     Payload keys: {list(msg_data.payload.keys())}")
                        #if 'data' in msg_data.payload:
                        #    print(f"[DEBUG]     Data content: {msg_data.payload.get('data')}")
                        all_responses[name] = msg_data.payload

                        # Also update the device object!
                        if port in manager.devices:
                            manager.devices[port].update_from_message(msg_data)
                        print(f"{C.OK}     Received capabilities and metadata from {name}.{C.END}")
                        break
        except queue.Empty:
            time.sleep(0.1)

    if len(all_responses) < len(device_ports):
        missing = [d for d in device_ports if d not in all_responses]
        print(f"{C.WARN}  -> Warning: Did not receive help response from: {missing}{C.END}")

    return all_responses