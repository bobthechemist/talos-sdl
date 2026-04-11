# host/ai/chat.py
import sys
import os
import argparse
from pathlib import Path

# Setup project root path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

# Core Talos Imports
from host.core.device_manager import DeviceManager
from dln import DigitalLabNotebook, ExperimentFinalizedError
from host.ai.llm_manager import LLMManager
from host.ai.ai_utils import connect_devices, get_instructions, load_world_from_file
from host.cogs.cog_manager import CogManager
from host.gui.console import C

class ChatApp:
    """The main Command and Control Center for the Talos-SDL Host."""
    def __init__(self, world_path: str, provider: str, model: str):
        # 1. Core Services
        self.world_model = load_world_from_file(world_path)
        if not self.world_model:
            raise RuntimeError("Failed to load world model. Cannot continue.")
        
        self.dln = DigitalLabNotebook(db_path=".talos/lab_notebook.db")
        self.session_id = self.dln.start_experiment(
            title=self.world_model.get('experiment_name', "Untitled"),
            context_json=self.world_model
        )
        self.active_data_session_id = self.session_id

        self.device_manager, self.device_ports = connect_devices()
        self.ai_commands, self.ai_guidance = get_instructions(self.device_manager, self.device_ports)

        # 2. State Management
        self.is_running = False
        self.current_mode = "run"
        self.require_confirmation = True
        self.ai_provider = provider
        self.ai_model = model
        self.ai_agent = None # Will be loaded by a cog
        
        # 3. Cog and Command Management
        self.commands = {}
        self.cog_manager = CogManager(self)
        self.cog_manager.load_cogs()

    def register_command(self, name, handler):
        """Callback for CogManager to register commands."""
        self.commands[name] = handler

    def run(self):
        """The main Read-Eval-Print-Loop (REPL) for user interaction."""

        self.is_running = True
        
        # Initial agent load by calling the mode handler
        print(f"{C.INFO}Initializing AI agent for default '{self.current_mode}' mode...{C.END}")

        self.commands["/mode"](self.current_mode)
        
        print(f"\n{C.INFO}System Online. Notebook Session: {self.session_id}.")
        print(f"Type /help for commands.{C.END}")

        try:
            while self.is_running:
                self._show_prompt()
                try:
                    user_input = input().strip()
                    if not user_input: continue
                    self._dispatch_command(user_input)
                except (KeyboardInterrupt, EOFError):
                    print(f"\n{C.WARN}Interrupted. Type /quit to exit.{C.END}")
        finally:
            self._shutdown()

    def _show_prompt(self):
        mode_str = "RUN" if self.current_mode == "run" else "DATA"
        prompt_color = C.WARN if mode_str == "RUN" else C.OK
        safety_char = "🔒" if self.require_confirmation else "⚡"
        
        prompt = f"\n{prompt_color}[{mode_str} S:{self.session_id} {safety_char}] > {C.END}"
        print(prompt, end="")

    def _dispatch_command(self, user_input: str):
        parts = user_input.split()
        command = parts[0].lower()
        args = parts[1:]

        handler = None
        if command.startswith("/"):
            handler = self.commands.get(command)
        else:
            # It's not a slash command, so use the default for the current mode
            default_command = "/run" if self.current_mode == "run" else "/data"
            handler = self.commands.get(default_command)
            args = user_input.split() # Pass the full input as args

        if handler:
            try:
                handler(*args)
            except Exception as e:
                print(f"{C.ERR}Error executing command '{command}': {e}{C.END}")
                # For debugging, you might want a traceback:
                # import traceback; traceback.print_exc()
        else:
            print(f"{C.ERR}Unknown command: {command}{C.END}")

    def _shutdown(self):
        print(f"\n{C.INFO}Shutting down...{C.END}")
        if self.dln.current_session_id is not None:
            self.dln.finalize(summary_text="User exited Cockpit.")
        self.device_manager.stop()
        print(f"{C.OK}Goodbye.{C.END}")

def main():
    parser = argparse.ArgumentParser(description="Talos-SDL Agentic Laboratory Cockpit")
    parser.add_argument("--world", default="world_model.json", help="Path to the world model configuration file.")
    parser.add_argument("--provider", default=os.getenv("AI_PROVIDER", "gemini"), help="AI Provider (gemini, ollama, openai).")
    parser.add_argument("--model", default=os.getenv("AI_MODEL", "gemini-1.5-flash-latest"), help="Specific model name.")
    args = parser.parse_args()

    print(f"\n{C.OK}==========================================")
    print("      Talos-SDL Agentic Laboratory Cockpit      ")
    print(f"=========================================={C.END}")

    try:
        app = ChatApp(world_path=args.world, provider=args.provider, model=args.model)
        app.run()
    except (RuntimeError, FileNotFoundError) as e:
        print(f"\n{C.ERR}A critical error occurred on startup: {e}{C.END}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{C.ERR}An unexpected error occurred: {e}{C.END}")
        import traceback; traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()