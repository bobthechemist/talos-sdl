# host/cogs/host_utility_cog.py
import time
from host.cogs.base_cog import BaseCog
from host.gui.console import C

class HostUtilityCog(BaseCog):
    """
    Provides universal host-side execution tools (e.g., wait) directly to 
    the AI planner and the ExecutionEngine.
    """
    def get_commands(self):
        # We don't expose any interactive chat commands (slash commands) right now.
        return {}

    def get_host_tools(self):
        """Registers the tool logic and its documentation for the AI prompt."""
        return {
            "wait": {
                "handler": self.execute_wait,
                "doc": {
                    "description": "Pauses plan execution for a specified number of seconds.",
                    "args": [
                        {"name": "seconds", "type": "float", "description": "Time to wait in seconds", "default": 1.0}
                    ],
                    "ai_enabled": True
                }
            }
        }

    def execute_wait(self, args: dict, plan_id: int, step_idx: int, engine, dln):
        """
        Pauses the execution thread for a given number of seconds.
        A Pythonic `None` return signals SUCCESS to the execution engine.
        """
        try:
            seconds = float(args.get("seconds", 1.0))
        except (ValueError, TypeError):
            # Raising an exception will automatically trigger a PROBLEM status in the engine
            raise ValueError(f"Invalid argument for 'seconds': {args.get('seconds')}")

        print(f" (waiting {seconds}s)...", end="", flush=True)
        time.sleep(seconds)
        
        # Implicitly returns None (Success)