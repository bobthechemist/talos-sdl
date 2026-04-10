from communicate.serial_postman import SerialPostman
from shared_lib.messages import Message
from ..firmware_db import get_device_name
import logging
import time

log = logging.getLogger(__name__)

class Device:
    """
    Represents the state and communication channel for a single connected instrument.
    This is the 'Model' in our MVC architecture. It is UI-agnostic.
    """
    def __init__(self, port, vid, pid):
        # --- Core Identity ---
        self.port = port
        self.vid = vid
        self.pid = pid
        self.postman = None
        
        # --- State Attributes (using standard Python types) ---
        self.friendly_name = get_device_name(vid, pid)
        self.firmware_name = "?"
        self.version = "?"
        self.current_state = "Connecting..."
        self.is_connected = False
        self.status_info = {}
        self.supported_commands = {}
        self.last_telemetry = {} # <-- ADDED: To store the most recent telemetry payload

    def connect(self):
        """Creates and opens the serial postman for this device."""
        if self.is_connected:
            return True
        try:
            params = {"protocol": "serial", "port": self.port, "baudrate": 115200, "timeout": 0.1}
            self.postman = SerialPostman(params)
            self.postman.open_channel()
            self.postman.channel.reset_input_buffer()
            self.is_connected = True
            self.current_state = "Connected"
            log.info(f"Device model for {self.port} connected successfully.")
            return True
        except Exception as e:
            self.current_state = "Connection Failed"
            log.error(f"Failed to connect Device model on {self.port}: {e}")
            return False

    def disconnect(self):
        """Closes the serial postman."""
        if self.postman and self.is_connected:
            self.postman.close_channel()
        self.is_connected = False
        self.current_state = "Disconnected"

    def send_message(self, message: Message):
        """Sends a message using this device's postman."""
        if not self.is_connected:
            raise RuntimeError("Cannot send message, device is not connected.")
        self.postman.send(message.serialize())

    # --- REVISED METHOD ---
    def update_from_message(self, msg: Message):
        """
        Updates the device's state based on an incoming message.
        """
        status = msg.status.upper()
        payload = msg.payload

        if status == 'DATA_RESPONSE':
            metadata = payload.get('metadata', {})
            data_content = payload.get('data', {})

            # --- Check for 'get_info' response (independent 'if') ---
            if 'firmware_name' in metadata:
                self.firmware_name = metadata.get('firmware_name', 'N/A')
                self.version = metadata.get('firmware_version', 'N/A')
                self.current_state = metadata.get('current_state', 'N/A')
                self.status_info = data_content
                log.info(f"[{self.port}] State updated from get_info: {self.firmware_name} v{self.version}, State: {self.current_state}")

            # --- Check for 'help' response (independent 'if') ---
            if (isinstance(data_content, dict) and data_content and
                isinstance(next(iter(data_content.values()), None), dict) and
                'description' in next(iter(data_content.values()), {})):

                self.supported_commands = data_content
                log.info(f"[{self.port}] Updated supported commands list ({len(self.supported_commands)} commands found).")

        elif status == 'TELEMETRY':
            log.debug(f"[{self.port}] Received telemetry: {payload}")
            # --- MODIFIED: Extract 'data' sub-dictionary if available ---
            self.last_telemetry = payload.get('data', payload)
            
        elif status == 'PROBLEM':
            log.warning(f"[{self.port}] Received PROBLEM: {payload}")