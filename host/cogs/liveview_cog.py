# host/cogs/liveview_cog.py
"""
LiveView Cog for Talos-SDL

Provides real-time sensor data visualization with live matplotlib plotting.
"""
from host.cogs.base_cog import BaseCog
from host.gui.console import C
from host.ai.live_view_manager import LiveViewManager, parse_field_spec


class LiveViewCog(BaseCog):
    """Provides live sensor data visualization with streaming graphs."""

    def __init__(self, app):
        super().__init__(app)
        # Initialize LiveViewManager with the app's device_manager
        self.live_view_manager = LiveViewManager(device_manager=self.device_manager)

    def get_commands(self):
        return {
            "/liveview": self.handle_liveview,
            "/stopview": self.handle_stopview,
        }

    def handle_liveview(self, *args):
        """
        Start live monitoring of device sensor data.

        Usage: /liveview                 - List available devices
               /liveview list            - List available devices
               /liveview <dev> list      - List available fields for device
               /liveview <dev> <fields>  - Start live monitoring

        Examples:
          /liveview magnetometer hmc5883.x
          /liveview magnetometer hmc5883.x hmc5883.y
          /liveview magnetometer list    - List available fields
          /liveview list                 - List available devices
        """
        # No arguments - list all devices
        if not args:
            self._list_devices()
            return

        device_name = args[0]

        # List available devices
        if device_name.lower() == "list":
            self._list_devices()
            return

        # Check if user wants to list fields for device
        if len(args) >= 2 and args[-1].lower() == "list":
            self._list_fields(device_name)
            return

        # Start a live view session
        if len(args) < 2:
            print(f"{C.ERR}Usage: /liveview <device_name> <field_spec>{C.END}")
            print(f"Use '/liveview {device_name} list' to see available fields.{C.END}")
            return

        field_spec = " ".join(args[1:])
        if not field_spec:
            print(f"{C.ERR}Invalid field specification.{C.END}")
            return

        # Parse field specifications (comma-separated or space-separated)
        field_specs = parse_field_spec(field_spec)

        if not field_specs:
            print(f"{C.ERR}Invalid field specification: {field_spec}{C.END}")
            return

        session_id, message = self.live_view_manager.start_session(device_name, field_specs)
        if session_id:
            print(f"{C.OK}{message}{C.END}")
        else:
            print(f"{C.ERR}{message}{C.END}")

    def handle_stopview(self, *args):
        """
        Stop the most recent live view session.
        """
        if not self.live_view_manager.sessions:
            print(f"{C.WARN}No active live view sessions.{C.END}")
            return

        session_id = list(self.live_view_manager.sessions.keys())[-1]
        if self.live_view_manager.stop_session(session_id):
            print(f"{C.OK}Stopped {session_id}{C.END}")
        else:
            print(f"{C.ERR}Failed to stop session.{C.END}")

    def _list_devices(self):
        """List all available devices with their ports, supported commands, and detected read command."""
        devices = self.live_view_manager.list_available_devices()
        print(f"\n{C.INFO}--- Available Devices ---{C.END}")
        if not devices:
            print("No devices connected.")
        else:
            for name, info in devices.items():
                print(f"  Device: {C.OK}{name}{C.END}")
                print(f"    Port: {info['port']}")
                if info.get('read_command'):
                    print(f"    Read Command: {C.WARN}{info['read_command']}{C.END}")
                if info['supported_commands']:
                    print(f"    Supported Commands: {', '.join(info['supported_commands'])}")
                print()

    def _list_fields(self, device_name):
        """List available data fields for a specific device."""
        fields = self.live_view_manager.get_device_fields(device_name)
        print(f"\n{C.INFO}--- Available Fields for '{device_name}' ---{C.END}")
        if fields is None:
            print(f"Device '{device_name}' not found.")
        elif not fields:
            print("No data fields available. Try sending a read command first.")
        else:
            for field in fields:
                print(f"  {C.OK}{field}{C.END}")
