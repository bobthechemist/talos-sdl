# host/cogs/cog_manager.py
import importlib
import inspect
from pathlib import Path
from host.cogs.base_cog import BaseCog
from host.gui.console import C

class CogManager:
    """
    Discovers, loads, and manages all Cogs for the ChatApp.
    """
    def __init__(self, app):
        self.app = app
        self.cogs_path = Path(__file__).parent
        self.loaded_cogs = {}

    def load_cogs(self):
        """
        Loads all cogs specified in the world model and registers their commands.

        - Loads all `required_cogs`.
        - Loads any `contextual_cogs` if their trigger device is connected.
        """
        print(f"{C.INFO}[+] Loading Cogs...{C.END}")
        world_model = self.app.world_model
        
        # 1. Load Required Cogs
        for cog_name in world_model.get("required_cogs", []):
            self._load_cog(cog_name)

        # 2. Load Contextual Cogs
        contextual_cogs = world_model.get("contextual_cogs", {})
        connected_devices = self.app.device_ports.keys()
        for device_trigger, cog_name in contextual_cogs.items():
            if device_trigger in connected_devices:
                print(f"{C.INFO}  -> Context match: Found '{device_trigger}', loading '{cog_name}'...{C.END}")
                self._load_cog(cog_name)
        
        print(f"{C.OK}[+] Cogs loaded: {list(self.loaded_cogs.keys())}{C.END}")

    def _load_cog(self, cog_name: str):
        """Dynamically imports and instantiates a single Cog class."""
        try:
            # Future-proofing: We can easily add a check here for `custom_cogs` later
            module_name = f"host.cogs.{cog_name}"
            cog_module = importlib.import_module(module_name)

            # Find the class in the module that inherits from BaseCog
            for name, obj in inspect.getmembers(cog_module, inspect.isclass):
                if issubclass(obj, BaseCog) and obj is not BaseCog:
                    cog_instance = obj(self.app)
                    self.loaded_cogs[cog_name] = cog_instance
                    
                    # 1. Register Slash Commands
                    commands = cog_instance.get_commands()
                    for cmd_name, handler in commands.items():
                        self.app.register_command(cmd_name, handler)
                    
                    # 2. Register Host Tools (AI facing)
                    host_tools = cog_instance.get_host_tools()
                    for tool_name, tool_data in host_tools.items():
                        self.app.host_tools[tool_name] = tool_data["handler"]
                        # Inject into the AI Prompt Dictionary so the AI knows it exists
                        self.app.ai_commands["host"][tool_name] = tool_data["doc"]
                    
                    tools_msg = f", Host Tools: {list(host_tools.keys())}" if host_tools else ""
                    print(f"  -> Successfully loaded Cog '{cog_name}' (Slash Cmds: {list(commands.keys())}{tools_msg})")
                    return

            print(f"{C.WARN}  -> Warning: No class inheriting from BaseCog found in '{cog_name}.py'.{C.END}")

        except ImportError:
            print(f"{C.ERR}  -> Error: Could not find or import cog '{cog_name}'. Please check the file exists.{C.END}")
            if cog_name in self.app.world_model.get("required_cogs", []):
                raise
        except Exception as e:
            print(f"{C.ERR}  -> Error loading cog '{cog_name}': {e}{C.END}")
            raise