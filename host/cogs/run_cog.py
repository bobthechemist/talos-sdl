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

# host/cogs/run_cog.py
    def handle_run(self, *args):
        goal = " ".join(args)
        if not goal:
            print(f"{C.ERR}Usage: /run <your goal here>{C.END}")
            return
        
        print(f"[*] Goal received: '{goal}'")
        self.dln.log_science(entry_type="intent", data={"goal": goal})
        
        prompt = self.prompt_factory.build_run_user_prompt(goal)
        print("[*] Thinking...")
        response = self.app.ai_agent.prompt(prompt, use_history=True)
        if not response: return

        ai_data = self._parse_ai_response(response)
        if not ai_data or "plan" not in ai_data: return
        
        # Initialize the Envelope
        envelope = {
            "intent": goal,
            "ai_proposal": ai_data.get("plan", []),
            "human_edits": [],
            "final_plan": ai_data.get("plan", [])
        }

        if self.app.require_confirmation:
            envelope = self._review_and_edit_plan(envelope)
            if envelope is None:
                print(f"{C.ERR}Plan rejected by user.{C.END}")
                return
        
        # Atomic log: record the envelope and execute
        self.dln.log_science(entry_type="plan", data=envelope)
        self.execution_engine.execute_plan(envelope["final_plan"])



    def _parse_ai_response(self, response):
        """Extracts a JSON object from the AI's response text."""
        json_str = response
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        return json.loads(json_str.strip())

    def _review_and_edit_plan(self, envelope):
            """Displays the plan and allows interactive editing with rationales."""
            plan = envelope["final_plan"]
            
            while True:
                print(f"\n{C.WARN}--- PLAN REVIEW (CTRL-C to abort) ---{C.END}")
                for idx, step in enumerate(plan):
                    dev = step.get('device', '?').upper()
                    cmd = step.get('command', '?')
                    args = json.dumps(step.get('args', {}))
                    print(f"  {C.INFO}{idx+1}.{C.END} {dev}: {cmd} {args}")

                print(f"\n{C.INFO}Actions: 'run', 'del <#> <rationale>', 'edit <#> <key=val> <rationale>', 'add <dev> <cmd> <args> <rationale>'{C.END}")
                
                user_input = input("Action > ").strip()
                if not user_input: continue
                
                parts = user_input.split(maxsplit=3)
                cmd = parts[0].lower()

                if cmd in ('run', 'y', 'yes'): return envelope
                if cmd in ('reject', 'n', 'no'): return None

                try:
                    if cmd == 'del' and len(parts) >= 2:
                        idx = int(parts[1]) - 1
                        rationale = parts[2] if len(parts) > 2 else "No rationale provided"
                        removed = plan.pop(idx)
                        envelope["human_edits"].append({"action": "del", "step": idx+1, "cmd": removed['command'], "rationale": rationale})
                        print(f"{C.WARN}Removed step {idx+1}.{C.END}")

                    elif cmd == 'edit' and len(parts) >= 3:
                        idx = int(parts[1]) - 1
                        # parts[2] is the key=val, parts[3] is the rationale
                        rationale = parts[3] if len(parts) > 3 else "No rationale provided"
                        new_args = self._parse_input_to_dict(parts[2])
                        plan[idx]['args'].update(new_args)
                        envelope["human_edits"].append({"action": "edit", "step": idx+1, "rationale": rationale})
                        print(f"{C.OK}Step {idx+1} updated.{C.END}")

                    elif cmd == 'add' and len(parts) >= 4:
                        dev, func, args_raw = parts[1], parts[2], parts[3]
                        rationale = "Manual addition"
                        new_step = {"device": dev, "command": func, "args": self._parse_input_to_dict(args_raw)}
                        plan.append(new_step)
                        envelope["human_edits"].append({"action": "add", "step": len(plan), "rationale": rationale})
                        print(f"{C.OK}Step added.{C.END}")
                    else:
                        print(f"{C.ERR}Invalid syntax. Ensure you provide a rationale for edits/deletes.{C.END}")
                except Exception as e:
                    print(f"{C.ERR}Error processing edit: {e}{C.END}")

    def _parse_input_to_dict(self, input_str: str) -> dict:
        """Parses 'key=val key2=val2' or standard JSON into a dictionary."""
        # 1. Try raw JSON
        if input_str.startswith("{"):
            return json.loads(input_str)
        
        # 2. Try key=value pairs
        result = {}
        pairs = input_str.split()
        for pair in pairs:
            if "=" not in pair: continue
            k, v = pair.split("=", 1)
            
            # Smart type inference
            try:
                # Attempt to parse as JSON (handles lists [1,2], bools, numbers)
                # We wrap in brackets to make simple types like '0.5' valid JSON
                val = json.loads(v)
            except json.JSONDecodeError:
                # Fallback to string if it's not valid JSON
                val = v
            
            result[k] = val
        return result