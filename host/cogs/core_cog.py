# host/cogs/core_cog.py
from host.cogs.base_cog import BaseCog
from host.gui.console import C

class CoreCog(BaseCog):
    """Handles essential, mode-agnostic application commands."""

    def get_commands(self):
        return {
            "/help": self.handle_help,
            "/quit": self.handle_quit,
            "/exit": self.handle_quit,
            "/clear": self.handle_clear,
        }

    def handle_help(self, *args):
        """Displays a list of all available slash commands."""
        print(f"\n{C.INFO}--- Available Commands ---{C.END}")
        # Access the registered commands from the main app
        for command in sorted(self.app.commands.keys()):
            # Get the handler function's docstring
            doc = self.app.commands[command].__doc__ or "No description available."
            print(f"  {C.OK}{command}{C.END:<25} : {doc.strip()}")
    
    def handle_quit(self, *args):
        """Finalizes the DLN session and safely exits the application."""
        print("Quit command received.")
        self.app.is_running = False # Signal the main loop to exit

    def handle_clear(self, *args):
        """Clears the current AI agent's short-term memory."""
        self.app.ai_agent.clear_history()
        mode_str = "RUN" if self.app.current_mode == "run" else "DATA"
        print(f"{C.INFO}Context cleared for {mode_str} mode.{C.END}")