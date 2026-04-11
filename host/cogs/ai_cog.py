# host/cogs/ai_cog.py
from host.cogs.base_cog import BaseCog
from host.gui.console import C
from host.ai.llm_manager import LLMManager
from host.ai.prompt_factory import PromptFactory

class AICog(BaseCog):
    """Provides aider-like control over the LLM's settings and modes."""

    def get_commands(self):
        return {
            "/provider": self.handle_provider,
            "/model": self.handle_model,
            "/mode": self.handle_mode,
            "/confirm": self.handle_confirm,
        }

    def handle_provider(self, *args):
        """Switches the AI provider (e.g., /provider gemini)."""
        if not args:
            print(f"{C.ERR}Usage: /provider <gemini|openai|ollama|...>{C.END}")
            return
        provider = args[0].lower()
        try:
            # This will test if the provider is valid without changing the model yet
            LLMManager.get_agent(provider=provider, model=self.app.ai_model)
            self.app.ai_provider = provider
            self._reload_agent()
            print(f"{C.OK}AI provider switched to: {self.app.ai_provider}{C.END}")
        except Exception as e:
            print(f"{C.ERR}Failed to switch provider: {e}{C.END}")

    def handle_model(self, *args):
        """Switches the AI model (e.g., /model gpt-4o)."""
        if not args:
            print(f"{C.ERR}Usage: /model <model_name>{C.END}")
            return
        model_name = args[0]
        self.app.ai_model = model_name
        self._reload_agent()
        print(f"{C.OK}AI model switched to: {self.app.ai_model}{C.END}")

    def handle_mode(self, *args):
        """Switches between 'run' and 'data' modes."""
        if not args or args[0].lower() not in ["run", "data"]:
            print(f"{C.ERR}Usage: /mode <run|data>{C.END}")
            return
        
        new_mode = args[0].lower()
        
        self.app.current_mode = new_mode
        self._reload_agent()
        
        mode_str = "RUN (Controller)" if self.app.current_mode == "run" else "DATA (Analyst)"
        
        if self.app.is_running:
            print(f"{C.INFO}Switched to {mode_str} mode.{C.END}")

    def handle_confirm(self, *args):
        """Toggles the human confirmation safety gate for /run commands."""
        if not args or args[0].lower() not in ["on", "off"]:
            self.app.require_confirmation = not self.app.require_confirmation
        else:
            self.app.require_confirmation = (args[0].lower() == "on")
        
        status = "ON 🔒" if self.app.require_confirmation else "OFF ⚡"
        print(f"{C.INFO}Safety Gate: {status}{C.END}")

    def _reload_agent(self):
        """Helper to reinstantiate the AI agent with current settings."""
        print(f"{C.INFO}Reloading AI agent for {self.app.current_mode} mode...{C.END}")
        prompt_factory = PromptFactory(self.app.world_model, self.app.ai_commands, self.app.ai_guidance)
        context = prompt_factory.get_system_prompt(self.app.current_mode)
        self.app.ai_agent = LLMManager.get_agent(
            provider=self.app.ai_provider,
            model=self.app.ai_model,
            context=context
        )