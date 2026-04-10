# host/ai/live_view_manager.py
"""
Live View Manager for Talos-SDL

Provides functionality to start, stop, and monitor live sensor data
in a separate matplotlib window with autoscaling graphs.
"""
import sys
import threading
import time
import queue
import uuid
import json
import re
from pathlib import Path
from collections import deque

# Setup project root path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from host.core.device_manager import DeviceManager
from shared_lib.messages import Message
from host.gui.console import C


class MatplotlibPlotManager:
    """Manages live view display in separate matplotlib window"""

    def __init__(self):
        """Initialize plot manager"""
        self.current_sessions = {}  # session_id -> session_data
        self.stop_plot_event = threading.Event()
        self.active = False
        self.figure = None
        self.axes = None
        self.lines = {}
        self.lock = threading.Lock()
        self._update_callback_id = None  # Track the after() callback ID
        self.close_callback = None  # Callback when window is closed

    def setup_plot(self, sessions):
        """
        Setup plot for display

        Args:
            sessions: List of LiveViewSession objects
        """
        try:
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
            import matplotlib.pyplot as plt
            import tkinter as tk

            # Only create window if it doesn't exist or is destroyed
            root_valid = False
            if hasattr(self, 'root') and self.root is not None:
                try:
                    if self.root.winfo_exists():
                        root_valid = True
                except Exception:
                    pass

            if not root_valid:
                self.stop_plot_event.clear()
                self.active = True

                # Create main window
                self.root = tk.Tk()
                self.root.title("Talos-SDL Live View")
                self.root.geometry("800x600")

                # Create matplotlib figure
                self.figure = plt.Figure(figsize=(8, 6), dpi=100)
                self.axes = self.figure.add_subplot(111)

                # Embed in tkinter
                self.canvas = FigureCanvasTkAgg(self.figure, master=self.root)
                self.canvas.draw()
                self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

                # Schedule periodic updates using after() - this ensures updates happen in main tkinter thread
                self._schedule_update()

                # Start background thread for window updates
                self.root_update_thread = threading.Thread(
                    target=self._update_root,
                    daemon=True
                )
                self.root_update_thread.start()

                # Add close handler to stop sessions when window is closed
                self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

            else:
                # Reuse existing window - nothing to do
                pass

            return True

        except Exception as e:
            print(f"{C.ERR}Error setting up display: {e}{C.END}")
            return False

    def _update_root(self):
        """Background thread to update tkinter window"""
        try:
            while not self.stop_plot_event.is_set():
                try:
                    if self.root and self.root.winfo_exists():
                        self.root.update()
                    time.sleep(0.05)  # 20 Hz update for window
                except Exception:
                    break
        except Exception:
            pass

    def _schedule_update(self):
        """Schedule periodic plot updates using tkinter after()"""
        try:
            # Don't schedule if plot manager is stopped or root doesn't exist
            if not self.active or not self.root or not self.root.winfo_exists():
                return

            # Cancel any pending callback first
            if self._update_callback_id:
                try:
                    self.root.after_cancel(self._update_callback_id)
                except Exception:
                    pass

            # Schedule update in the main tkinter thread
            self._update_callback_id = self.root.after(100, self._do_update_plots)
        except Exception:
            pass

    def _do_update_plots(self):
        """Actually update plots - called from main tkinter thread"""
        try:
            with self.lock:
                if not self.current_sessions:
                    return

                # Update each session's plot
                for session_id, session_data in self.current_sessions.items():
                    self._update_session_plot(session_id, session_data)

                # Redraw canvas
                if self.canvas and self.figure:
                    self.canvas.draw()

        except Exception as e:
            print(f"{C.ERR}Plot update error: {e}{C.END}")

        # Schedule next update
        self._schedule_update()

    def _update_session_plot(self, session_id, session_data):
        """
        Update plot for a single session

        Args:
            session_id: Session identifier
            session_data: Dictionary with session data
        """
        if not self.axes:
            return

        # Get latest data
        data_buffer = session_data['data_buffer']
        if not data_buffer:
            return

        # Get field labels from session data
        field_labels = session_data.get('field_labels', [])
        if not field_labels:
            return

 
        # Get the last N samples that fit in the plot
        max_samples = 20
        sample_numbers = session_data['sample_numbers'][-max_samples:]

        if not sample_numbers:
            return

        # Extract data for each field being plotted, matching the sample count
        field_data = {}
        for field in field_labels:
            values = []
            # Only include values for samples we're plotting
            for entry in data_buffer:
                value = self._get_nested_value(entry, field)
                if value is not None:
                    values.append(value)
            # Trim to match sample_numbers
            field_data[field] = values[-max_samples:]

        # Clear previous plot
        self.axes.clear()

        # Set up plot
        self.axes.set_title(f"Live Sensor Data - {session_id}", fontsize=10, fontweight='bold')
        self.axes.set_xlabel("Sample Number", fontsize=8)
        self.axes.set_ylabel("Value", fontsize=8)
        self.axes.grid(True, linestyle='--', alpha=0.7)

        # Colors for different fields
        colors = ['b', 'g', 'r', 'c', 'm', 'y', 'k']
        markers = ['-', '-', '-', '--', '--', '--', '-.']
        labels = []
        plotted_fields = []

        # Plot each field
        for i, (field, values) in enumerate(field_data.items()):
            color = colors[i % len(colors)]
            marker = markers[i % len(markers)]
            label = field.replace('_', ' ').title()

            if values:
                # Truncate sample_numbers to match values length
                plot_samples = sample_numbers[-len(values):]
                self.axes.plot(plot_samples, values, color + marker,
                             label=label, linewidth=1.5, markersize=3)
                labels.append(label)
                plotted_fields.append(field)

        # Autoscale with limits
        self.axes.relim()
        self.axes.autoscale_view()

        # Set reasonable y-axis limits
        all_values = []
        for values in field_data.values():
            all_values.extend(values)
        if all_values:
            min_val = min(all_values)
            max_val = max(all_values)
            margin = (max_val - min_val) * 0.1 if max_val != min_val else 1.0
            self.axes.set_ylim(min_val - margin, max_val + margin)

        # Add legend
        if labels:
            self.axes.legend(loc='upper left', fontsize=7, framealpha=0.9)

        # Set x-axis limits to show last 20 samples
        if sample_numbers:
            self.axes.set_xlim(sample_numbers[0], sample_numbers[-1])

    def _get_nested_value(self, data, field_path):
        """
        Get a nested value from a dictionary using dot notation.
        Case-insensitive key matching for field paths.
        Also searches inside 'raw_data' sub-dictionary if first level doesn't match.

        Args:
            data: Dictionary to search
            field_path: Dot notation path (e.g., 'hmc5883.x')

        Returns:
            Value at the path, or None if not found
        """
        parts = field_path.split('.')

        # First, try to find at top level
        value = data
        for part in parts:
            if isinstance(value, dict):
                for key in value.keys():
                    if key.lower() == part.lower():
                        value = value[key]
                        break
                else:
                    # Top level not found, try inside 'raw_data'
                    if 'raw_data' in data and isinstance(data['raw_data'], dict):
                        return self._get_nested_value(data['raw_data'], field_path)
                    return None
            else:
                return None

        # Convert to float if possible
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def update_session_data(self, session_id, data):
        """
        Update session data for plotting

        Args:
            session_id: Session identifier
            data: Dictionary with session data
        """
        with self.lock:
            self.current_sessions[session_id] = data

    def clear_session(self, session_id):
        """Clear data for a specific session"""
        with self.lock:
            if session_id in self.current_sessions:
                del self.current_sessions[session_id]

    def stop(self):
        """Stop plot updates"""
        self.active = False  # Prevent further scheduling
        try:
            # Cancel any pending callback
            if self._update_callback_id and self.root:
                try:
                    self.root.after_cancel(self._update_callback_id)
                except Exception:
                    pass
            if self.root and self.root.winfo_exists():
                self.root.quit()
                self.root.destroy()
        except Exception as e:
            print(f"{C.ERR}Error stopping plot: {e}{C.END}")

        self.current_sessions.clear()
        print()  # Move to next line after stopping
        self._update_callback_id = None

    def _on_window_close(self):
        """Called when the matplotlib window is closed by user"""
        # Call the close callback if set
        if self.close_callback:
            self.close_callback()


class LiveViewSession:
    """Manages a single live view session"""

    def __init__(self, device_name, port, field_specs, manager, plot_manager):
        """
        Initialize live view session

        Args:
            device_name: Name of the device (e.g., 'magnetometer')
            port: Serial port identifier
            field_specs: List of field specifications (e.g., ['hmc5883.x', 'hmc5883.y'])
            manager: DeviceManager instance
            plot_manager: MatplotlibPlotManager instance
        """
        self.device_name = device_name
        self.port = port
        self.field_specs = field_specs
        self.manager = manager
        self.plot_manager = plot_manager
        self.session_id = f"session_{uuid.uuid4().hex[:8]}"

        # Data buffer (last 20 samples)
        self.data_buffer = []
        self.max_samples = 20

        # Session state
        self.active = False
        self.stop_event = threading.Event()
        self.sample_numbers = []
        self.lock = threading.Lock()

    def start(self):
        """Start the live view session"""
        self.active = True
        self.stop_event.clear()

        # Initialize plot manager with session
        self.plot_manager.current_sessions[self.session_id] = {
            'data_buffer': [],
            'sample_numbers': [],
            'field_labels': self.field_specs
        }

        # Start sampling thread
        self.sample_thread = threading.Thread(
            target=self._sample_thread,
            daemon=True
        )
        self.sample_thread.start()

    def stop(self):
        """Stop the live view session"""
        self.active = False
        self.stop_event.set()
        if hasattr(self, 'sample_thread'):
            self.sample_thread.join(timeout=1)
        # Clear from plot manager
        self.plot_manager.clear_session(self.session_id)

    def _sample_thread(self):
        """Background thread for sampling at 5 Hz"""
        while not self.stop_event.is_set():
            try:
                # Send read_now command to get current sensor reading
                read_msg = Message.create_message(
                    subsystem_name=self.device_name,
                    status="INSTRUCTION",
                    payload={"func": "read_now", "args": {}}
                )
                self.manager.send_message(self.port, read_msg)

                # Wait for DATA_RESPONSE
                # This is handled by DeviceManager's incoming_message_queue
                # We need to wait for the specific message for this port
                start_time = time.time()
                timeout = 0.5  # 0.5 second timeout

                while time.time() - start_time < timeout:
                    try:
                        msg_type, msg_port, msg_data = self.manager.incoming_message_queue.get(timeout=0.05)

                        if msg_port == self.port and msg_data.status == "DATA_RESPONSE":
                            # Process the data
                            payload = msg_data.payload
                            self._process_data(payload)
                            break

                    except queue.Empty:
                        # Timeout waiting for response
                        break

            except Exception as e:
                print(f"{C.ERR}Sampling error: {e}{C.END}")
                break

            # 5 Hz = 200ms interval
            time.sleep(0.2)

    def _process_data(self, payload):
        """
        Process sensor data from firmware

        Args:
            payload: Payload dictionary from firmware
        """
        with self.lock:
            try:
                metadata = payload.get('metadata', {})
                data = payload.get('data', {})

                # Extract sample number and timestamp
                sample_number = metadata.get('sample_number', len(self.sample_numbers))
                timestamp = metadata.get('timestamp', time.time())

                # Create entry with raw data
                entry = {
                    'sample_number': sample_number,
                    'timestamp': timestamp,
                    'raw_data': data
                }

                # Update sample numbers
                if sample_number not in self.sample_numbers:
                    self.sample_numbers.append(sample_number)

                # Keep only last 20 samples
                if len(self.data_buffer) >= self.max_samples:
                    self.data_buffer.pop(0)

                self.data_buffer.append(entry)

                # Update plot manager with latest data
                self.plot_manager.update_session_data(
                    self.session_id,
                    {
                        'data_buffer': self.data_buffer,
                        'sample_numbers': self.sample_numbers,
                        'field_labels': self.field_specs
                    }
                )

            except Exception as e:
                print(f"{C.ERR}Error processing data: {e}{C.END}")


class LiveViewManager:
    """Global session registry and API"""

    def __init__(self, device_manager=None):
        """
        Initialize live view manager

        Args:
            device_manager: Optional DeviceManager instance to use for device discovery
        """
        self.sessions = {}  # session_id -> LiveViewSession
        self.manager = device_manager if device_manager else DeviceManager()
        self.plot_manager = MatplotlibPlotManager()
        # Set callback to stop all sessions when window is closed
        self.plot_manager.close_callback = self._on_plot_window_close

    def start_session(self, device_name, field_specs):
        """
        Start a live view session for specified device and fields

        Args:
            device_name: Name of the device (e.g., 'magnetometer')
            field_specs: List of field specifications (e.g., ['hmc5883.x', 'hmc5883.y'])

        Returns:
            Tuple of (session_id, status_message)
            Returns (None, error_message) on failure
        """
        if not device_name:
            return None, "Error: Device name is required"

        if not field_specs:
            return None, "Error: At least one field specification is required"

        # Find device port by name
        device_port = self._get_device_port_by_name(device_name)

        if device_port is None:
            return None, f"Error: No device found with name '{device_name}'"

        # Create and start session
        session = LiveViewSession(
            device_name=device_name,
            port=device_port,
            field_specs=field_specs,
            manager=self.manager,
            plot_manager=self.plot_manager
        )
        session.start()

        # Generate unique session ID
        session_id = f"session_{uuid.uuid4().hex[:8]}"

        # Store session
        self.sessions[session_id] = session

        # Start plot if not already running or if window was destroyed
        plot_root = getattr(self.plot_manager, 'root', None)
        needs_setup = True  # Default to True if root is None or invalid
        try:
            if plot_root and plot_root.winfo_exists():
                needs_setup = False
        except Exception:
            # winfo_exists() failed, assume root is destroyed
            needs_setup = True
        if needs_setup:
            self.plot_manager.active = True  # Reset active flag before setup
            self.plot_manager.setup_plot(list(self.sessions.values()))

        return session_id, f"Live view started: {session_id}"

    def stop_session(self, session_id):
        """
        Stop a live view session

        Args:
            session_id: Session identifier

        Returns:
            True if stopped, False otherwise
        """
        if session_id not in self.sessions:
            return False

        # Stop the session
        self.sessions[session_id].stop()

        # Remove from registry
        del self.sessions[session_id]

        # Check if any sessions remain
        if not self.sessions:
            # Stop plot if no sessions left
            self.plot_manager.stop()

        return True

    def cleanup_all(self):
        """Stop all active live view sessions"""
        for session_id in list(self.sessions.keys()):
            self.stop_session(session_id)

    def _on_plot_window_close(self):
        """Callback when the plot window is closed - stops all sessions"""
        # Stop all sessions and print messages for each stopped session
        for session_id in list(self.sessions.keys()):
            if self.stop_session(session_id):
                print(f"{C.OK}Stopped {session_id}{C.END}")
        # Print newline for clarity
        print()

    def _get_display_name(self, device):
        """
        Get a display-friendly name for a device.

        If firmware_name is available and not the default "?", use it (e.g., "Magnetometer").
        Otherwise, extract from friendly_name (e.g., "Magnetometer (WildCircuits)" -> "Magnetometer").

        Args:
            device: Device instance

        Returns:
            Display name string
        """
        # Use firmware_name if available and not default
        if device.firmware_name != "?":
            return device.firmware_name

        # Extract from friendly_name by removing parenthetical info
        # e.g., "Magnetometer (WildCircuits)" -> "Magnetometer"
        if device.friendly_name:
            if '(' in device.friendly_name:
                return device.friendly_name.split('(')[0].strip()
            return device.friendly_name

        return device.port

    def list_available_devices(self):
        """
        List available devices and their data fields

        Returns:
            Dictionary with device information
        """
        devices = {}
        for port, device in self.manager.devices.items():
            display_name = self._get_display_name(device)
            devices[display_name] = {
                'port': port,
                'supported_commands': list(device.supported_commands.keys()) if device.supported_commands else []
            }
        return devices

    def _get_device_port_by_name(self, device_name):
        """
        Find device port by device name

        Args:
            device_name: Name of the device to find (e.g., "magnetometer")

        Returns:
            Serial port identifier or None
        """
        for port, device in self.manager.devices.items():
            # Get display name for matching
            name = self._get_display_name(device)
            if name and device_name.lower() in name.lower():
                return port
        return None

    def get_device_fields(self, device_name):
        """
        Get available data fields for a device

        Args:
            device_name: Name of the device

        Returns:
            List of available field paths (e.g., ['hmc5883.x', 'hmc5883.y'])
            or None if device not found
        """
        port = self._get_device_port_by_name(device_name)
        if not port:
            return None

        # Request a sample to see what fields are available
        # Send a read command and check the response structure
        read_msg = Message.create_message(
            subsystem_name=device_name,
            status="INSTRUCTION",
            payload={"func": "read_now", "args": {}}
        )
        self.manager.send_message(port, read_msg)

        # Wait briefly for response
        start_time = time.time()
        while time.time() - start_time < 1.0:
            try:
                msg_type, msg_port, msg_data = self.manager.incoming_message_queue.get(timeout=0.1)
                if msg_port == port and msg_data.status == "DATA_RESPONSE":
                    data = msg_data.payload.get('data', {})
                    return self._extract_field_paths(data)
            except queue.Empty:
                continue

        return None

    def _extract_field_paths(self, data, prefix=''):
        """
        Extract all field paths from a nested dictionary

        Args:
            data: Dictionary to extract paths from
            prefix: Current path prefix

        Returns:
            List of field paths (e.g., ['hmc5883.x', 'hmc5883.y'])
        """
        paths = []
        if isinstance(data, dict):
            for key, value in data.items():
                new_prefix = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    paths.extend(self._extract_field_paths(value, new_prefix))
                else:
                    paths.append(new_prefix)
        return paths


def parse_field_spec(spec):
    """
    Parse a field specification string

    Args:
        spec: String like 'hmc5883.x' or 'hmc5883.x, hmc5883.y' or 'hmc5883.x hmc5883.y'

    Returns:
        List of field specifications (e.g., ['hmc5883.x', 'hmc5883.y'])
    """
    if not spec:
        return []

    # First split by comma
    parts = spec.split(',')
    result = []
    for part in parts:
        # Then split each part by whitespace and add non-empty items
        result.extend([p.strip() for p in part.split() if p.strip()])
    return result


if __name__ == "__main__":
    # Test code
    print("Live View Manager module loaded")
