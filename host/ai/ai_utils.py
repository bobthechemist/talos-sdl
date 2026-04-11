# host/ai/ai_utils.py
import sys
import time
import queue
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

def load_world_from_file(filepath: str):
    """Loads a world model from a specified JSON file."""
    print(f"\n{C.INFO}[+] Loading world model from '{filepath}'...{C.END}")
    try:
        with open(filepath, 'r') as f:
            world_model = json.load(f)
        print(f"{C.OK}  -> World model loaded successfully.{C.END}")
        return world_model
    except FileNotFoundError:
        print(f"{C.ERR}  -> Error: World file not found at '{filepath}'.{C.END}")
        return None
    except json.JSONDecodeError as e:
        print(f"{C.ERR}  -> Error: Could not parse world file. Invalid JSON: {e}{C.END}")
        return None

def connect_devices():
    """
    Scans for and connects to ANY recognized Talos devices found in firmware_db.py.
    
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
        
        if "Unknown" not in friendly_name:
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
        print(f"{C.OK}[+] Connected to: {list(device_ports_map.keys())}{C.END}")
        
    return manager, device_ports_map

def get_instructions(manager: DeviceManager, device_ports: dict, timeout: int = 5):
    """
    Sends 'help' commands to all connected devices and returns their full capabilities.
    
    Returns:
        tuple: (dict of ai_enabled_commands, dict of ai_guidance)
    """
    if not device_ports: return {}, {}

    print(f"\n{C.INFO}[+] Retrieving capabilities from {len(device_ports)} device(s)...{C.END}")
    help_message = Message.create_message("AI_HOST", "INSTRUCTION", payload={"func": "help", "args": {}})
    for port in device_ports.values():
        manager.send_message(port, help_message)

    full_caps = {}
    start_time = time.time()
    
    while len(full_caps) < len(device_ports) and time.time() - start_time < timeout:
        try:
            msg_type, port, msg_data = manager.incoming_message_queue.get_nowait()
            if msg_type == 'RECV' and msg_data.status == "DATA_RESPONSE":
                for name, p in device_ports.items():
                    if p == port and name not in full_caps:
                        full_caps[name] = msg_data.payload
                        print(f"     {C.OK}Received capabilities from {name}.{C.END}")
                        break
        except queue.Empty:
            time.sleep(0.1)

    ai_commands = {}
    ai_guidance = {}
    for dev, payload in full_caps.items():
        ai_commands[dev] = {k: v for k, v in payload.get('data', {}).items() if v.get('ai_enabled', False)}
        ai_guidance[dev] = payload.get('metadata', {}).get('ai_guidance', "")

    if len(full_caps) < len(device_ports):
        missing = [d for d in device_ports if d not in full_caps]
        print(f"{C.WARN}  -> Warning: Did not receive help response from: {missing}{C.END}")

    return ai_commands, ai_guidance