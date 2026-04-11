# host/cogs/run_cog.py
import json
from host.cogs.base_cog import BaseCog
from host.gui.console import C
from host.ai.prompt_factory import PromptFactory
from host.ai.execution_engine import ExecutionEngine

class RunCog(BaseCog):
    """Encapsulates the entire 'run' mode workflow for executing tasks."""

    def __init__(self, app):
        super().__init__(app)
        self.prompt_factory = PromptFactory(app.world_model, app.ai_commands, app.ai_guidance)
        self.execution_engine = ExecutionEngine(app.device_manager, app.device_ports, app.dln)

    def get_commands(self):
        return {"/run": self.handle_run}

    def handle_run(self, *args):
        """Executes a user's goal by planning and running hardware commands."""
        goal = " ".join(args)
        if not goal:
            print(f"{C.ERR}Usage: /run <your goal here>{C.END}")
            return
        
        print(f"[*] Goal received: '{goal}'")
        self.dln.log_science(entry_type="intent", data={"goal": goal})
        
        prompt = self.prompt_factory.build_run_user_prompt(goal)
        print("[*] Thinking...")
        response = self.app.ai_agent.prompt(prompt, use_history=True)
        if not response:
            print(f"{C.ERR}AI did not return a response.{C.END}")
            return

        try:
            ai_data = self._parse_ai_response(response)
            if not ai_data or "plan" not in ai_data:
                print(f"{C.ERR}AI response was not a valid plan.{C.END}\nResponse: {response}")
                return
        except json.JSONDecodeError:
            print(f"{C.ERR}Failed to parse AI response as JSON.{C.END}\nResponse: {response}")
            return
        
        plan = ai_data.get("plan", [])

        if self.app.require_confirmation:
            plan = self._review_and_edit_plan(plan)
            if plan is None:
                print(f"{C.ERR}Plan rejected by user.{C.END}")
                return
        
        self.dln.log_science(entry_type="plan", data={"plan": plan})
        self.execution_engine.execute_plan(plan)

    def _parse_ai_response(self, response):
        """Extracts a JSON object from the AI's response text."""
        json_str = response
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        return json.loads(json_str.strip())

    def _review_and_edit_plan(self, plan):
        """Displays the plan for human-in-the-loop review and editing."""
        while True:
            print(f"\n{C.WARN}--- PLAN REVIEW (CTRL-C to abort) ---{C.END}")
            if not plan: print(f"  {C.ERR}(Plan is empty){C.END}")
            else:
                for idx, step in enumerate(plan):
                    dev = step.get('device', '?').upper()
                    cmd = step.get('command', '?')
                    args = json.dumps(step.get('args', {}))
                    print(f"  {C.INFO}{idx+1}.{C.END} {dev}: {cmd} {args}")

            print(f"\n{C.INFO}Actions: 'run' (or y), 'reject' (or n), 'edit <#>', 'del <#>', 'add'{C.END}")
            try:
                user_input = input("Action > ").strip().lower()
                if user_input in ('run', 'y', 'yes'): return plan
                if user_input in ('reject', 'no', 'n'): return None
                # Add logic for edit, del, add here if needed, following old implementation
            except (EOFError, KeyboardInterrupt):
                return None