# host/cogs/base_cog.py

class BaseCog:
    """
    The base class for all Cogs. Cogs are modular plugins that add slash commands
    and functionality to the main ChatApp.
    """
    def __init__(self, app):
        """
        Initializes the Cog with a reference to the main application.

        Args:
            app: The main ChatApp instance, providing access to core services
                 like the dln, device_manager, and ai_agent.
        """
        self.app = app
        self.dln = app.dln
        self.device_manager = app.device_manager
        # Note: AI agent is accessed via self.app.ai_agent as it can change

    def get_commands(self):
        """
        Must be implemented by subclasses.

        Returns:
            dict: A dictionary mapping a command name (e.g., "/help") to its
                  handler method (e.g., self.handle_help).
        """
        raise NotImplementedError("Cogs must implement get_commands()")