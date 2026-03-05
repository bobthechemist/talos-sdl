import json
import time
import serial
import serial.tools.list_ports

class TalosLite:
    """
    A lightweight, standalone interface for Talos-SDL instruments.
    Zero dependencies on the main Talos codebase. 
    Requires: pip install pyserial
    """

    # Default Vendor ID for Brockport Original Builds
    DEFAULT_VID = 808 
    
    # Map of PIDs from firmware_db.py for convenience
    PRODUCTS = {
        810: "Fake Device",
        811: "Stirplate Manager",
        812: "Sidekick",
        813: "Colorimeter"
    }

    def __init__(self, port=None, vid=DEFAULT_VID, pid=None, timeout=1.0):
        """
        Initialize connection. If port is None, it attempts to auto-discover
        based on VID and PID.
        """
        self.port = port
        self.vid = vid
        self.pid = pid
        self.serial = None
        self.timeout = timeout
        self.subsystem_name = "PYTHON_LITE"

        if self.port is None:
            self.port = self.discover_port()

    def discover_port(self):
            """
            Finds the CircuitPython Data port matching VID/PID.
            Filters out the Console/REPL port.
            """
            # Get all ports and sort them so COM32 comes before COM33
            ports = sorted(serial.tools.list_ports.comports())
            matches = []
            
            for p in ports:
                if p.vid == self.vid:
                    if self.pid is None or p.pid == self.pid:
                        matches.append(p)
            
            if not matches:
                return None

            # If we found two ports for the same device, CircuitPython standard 
            # convention is that the higher interface/port number is the DATA port.
            if len(matches) > 1:
                # Heuristic 1: Check for 'CircuitPython CDC control' or interface index
                # Interface 0 is Console, Interface 2 is Data.
                for m in matches:
                    # On many systems, the data port location ends in '.2' or 'mi_02'
                    if m.location and ('mi_02' in m.location.lower() or m.location.endswith('.2')):
                        print(f"[*] Auto-discovered Data Port (via location) on {m.device}")
                        return m.device
                
                # Fallback Heuristic 2: If we have exactly two, pick the higher COM number
                data_port = matches[-1] # The sorted last item
                print(f"[*] Auto-discovered Data Port (via index) on {data_port.device}")
                return data_port.device
                
            # If only one port found, it might be the only one enabled
            return matches[0].device

    def connect(self):
        """Opens the serial connection."""
        if not self.port:
            raise IOError("No port specified and auto-discovery failed.")
        
        self.serial = serial.Serial(self.port, 115200, timeout=self.timeout)
        # Flush buffers to clear boot messages
        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        time.sleep(1) # Allow connection to stabilize
        print(f"[+] Connected to {self.port}")

    def disconnect(self):
        """Closes the serial connection."""
        if self.serial and self.serial.is_open:
            self.serial.close()
            print("[-] Disconnected.")

    def send(self, func, args=None):
        """Sends an INSTRUCTION packet."""
        message = {
            "timestamp": time.time(),
            "subsystem_name": self.subsystem_name,
            "status": "INSTRUCTION",
            "payload": {
                "func": func,
                "args": args or {}
            }
        }
        raw_payload = json.dumps(message) + "\n"
        self.serial.write(raw_payload.encode('utf-8'))

    def receive(self, timeout=None):
        """
        Reads the next JSON message from the instrument.
        Returns a dict or None if timeout.
        """
        if timeout:
            self.serial.timeout = timeout
        
        line = self.serial.readline()
        if not line:
            return None
            
        try:
            return json.loads(line.decode('utf-8').strip())
        except json.JSONDecodeError:
            return {"status": "RAW", "payload": line}

    def call(self, func, args=None, wait_status=("SUCCESS", "DATA_RESPONSE", "PROBLEM")):
        """
        Synchronous helper: Sends a command and waits for a specific response status.
        Ignores intermediate TELEMETRY messages.
        """
        self.send(func, args)
        start_time = time.time()
        
        while (time.time() - start_time) < 30: # 30s hard timeout
            msg = self.receive()
            if not msg:
                continue
            
            status = msg.get("status")
            if status in wait_status:
                return msg
            elif status == "TELEMETRY":
                continue # Ignore periodic telemetry
                
        return {"status": "ERROR", "payload": "Timed out waiting for response"}

# --- Usage Example (Standard Python or Jupyter) ---
if __name__ == "__main__":
    # Example: Connect to the stirplate
    # You can specify the PID (811) to ensure you hit the right device
    try:
        lab = TalosLite(pid=811) 
        lab.connect()

        # 1. Simple Ping
        print("Pinging...")
        print(lab.call("ping"))

        # 2. Get Info
        print("\nGetting Device Info...")
        info = lab.call("get_info")
        print(json.dumps(info, indent=2))

        # 3. Control Action
        print("\nSetting Stirplate Speed...")
        # Note: Handlers expect args in a dict
        resp = lab.call("set_speed", {"motor_id": 1, "speed": 0.5})
        print(resp)

        time.sleep(2)

        print("\nStopping all...")
        lab.call("stop_all")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'lab' in locals():
            lab.disconnect()