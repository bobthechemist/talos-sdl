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
        if not response: return

        ai_data = self._parse_ai_response(response)
        if not ai_data or "plan" not in ai_data: return
        
        proposal = ai_data.get("plan", [])
        
        envelope = {
            "intent": goal,
            "ai_proposal": list(proposal), 
            "human_edits": [],
            "final_plan": list(proposal)
        }

        if self.app.require_confirmation:
            envelope = self._review_and_edit_plan(envelope)
            if envelope is None:
                print(f"{C.ERR}Plan rejected by user.{C.END}")
                return
        
        # Log the plan and capture the returned ID
        plan_id = self.dln.log_science(entry_type="plan", data=envelope)
        
        # Pass the plan_id to the execution engine
        self.execution_engine.execute_plan(envelope["final_plan"], plan_id=plan_id)



    def _parse_ai_response(self, response):
        """Extracts a JSON object from the AI's response text."""
        json_str = response
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        return json.loads(json_str.strip())

    def _review_and_edit_plan(self, envelope):
        """Displays the plan for human-in-the-loop review and editing."""
        plan = envelope["final_plan"]
        while True:
            print(f"\n{C.WARN}--- PLAN REVIEW (CTRL-C to abort) ---{C.END}")
            if not plan:
                print(f"  {C.ERR}(Plan is empty){C.END}")
            else:
                for idx, step in enumerate(plan):
                    dev = step.get('device', '?').upper()
                    cmd = step.get('command', '?')
                    args = json.dumps(step.get('args', {}))
                    print(f"  {C.INFO}{idx+1}.{C.END} {dev}: {cmd} {args}")

            print(f"\n{C.INFO}Actions: 'run', 'del <#> <rationale>', 'edit <#> <key=val> <rationale>', 'add <dev> <cmd> <args> <rationale>'{C.END}")
            
            user_input = input("Action > ").strip()
            if not user_input: continue
            
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            rest = parts[1] if len(parts) > 1 else ""

            if cmd in ('run', 'y', 'yes'): 
                return envelope
            if cmd in ('reject', 'n', 'no'): 
                return None

            try:
                if cmd == 'del':
                    sub_parts = rest.split(maxsplit=1)
                    idx = int(sub_parts[0]) - 1
                    rationale = sub_parts[1] if len(sub_parts) > 1 else "No rationale provided"
                    
                    removed = plan.pop(idx)
                    envelope["human_edits"].append({
                        "action": "del", 
                        "step": idx + 1, 
                        "cmd": removed['command'], 
                        "rationale": rationale
                    })
                    print(f"{C.WARN}Removed step {idx+1}.{C.END}")

                elif cmd == 'edit':
                    sub_parts = rest.split(maxsplit=2)
                    idx = int(sub_parts[0]) - 1
                    args_str = sub_parts[1]
                    rationale = sub_parts[2] if len(sub_parts) > 2 else "No rationale provided"
                    
                    new_args = self._parse_input_to_dict(args_str)
                    plan[idx]['args'].update(new_args)
                    envelope["human_edits"].append({
                        "action": "edit", 
                        "step": idx + 1, 
                        "rationale": rationale
                    })
                    print(f"{C.OK}Step {idx+1} updated.{C.END}")

                elif cmd == 'add':
                    sub_parts = rest.split(maxsplit=3)
                    dev, func, args_raw = sub_parts[0], sub_parts[1], sub_parts[2]
                    rationale = sub_parts[3] if len(sub_parts) > 3 else "Manual addition"
                    
                    new_step = {
                        "device": dev, 
                        "command": func, 
                        "args": self._parse_input_to_dict(args_raw)
                    }
                    plan.append(new_step)
                    envelope["human_edits"].append({
                        "action": "add", 
                        "step": len(plan), 
                        "rationale": rationale
                    })
                    print(f"{C.OK}Step added.{C.END}")
                else:
                    print(f"{C.ERR}Unknown command '{cmd}'.{C.END}")
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