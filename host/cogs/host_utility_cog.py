# host/cogs/host_utility_cog.py
import time
import json
from host.cogs.base_cog import BaseCog
from host.gui.console import C

class HostUtilityCog(BaseCog):
    """
    Provides universal host-side execution tools directly to 
    the AI planner and the ExecutionEngine.
    """
    def get_commands(self):
        return {}

    def get_host_tools(self):
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
            },
            "submit_intent": {
                "handler": self.execute_submit_intent,
                "doc": {
                    "description": "Passes the baton back to the AI planner to generate follow-up steps. Use this for conditional logic or optimization based on data just collected.",
                    "args": [
                        {"name": "intent", "type": "str", "description": "The follow-up prompt (e.g. 'If VOC < 200, turn pixel 0 green, else red' or 'Move to the angle with highest VOC')."}
                    ],
                    "ai_enabled": True
                }
            }
        }

    def execute_wait(self, args: dict, plan_id: int, step_idx: int, engine, app):
        try:
            seconds = float(args.get("seconds", 1.0))
        except (ValueError, TypeError):
            raise ValueError(f"Invalid argument for 'seconds': {args.get('seconds')}")

        print(f" (waiting {seconds}s)...", end="", flush=True)
        time.sleep(seconds)

    def execute_submit_intent(self, args: dict, plan_id: int, step_idx: int, engine, app):
        intent = args.get("intent")
        if not intent:
            raise ValueError("Missing 'intent' argument.")

        print(f"\n{C.INFO}[*] Handing off to AI: '{intent}'{C.END}")

        # 1. Gather all observations collected during THIS SPECIFIC plan
        sql = f"""
            SELECT data FROM ScienceLog 
            WHERE session_id = {app.dln.current_session_id} 
              AND entry_type = 'observation' 
              AND json_extract(data, '$.plan_metadata.plan_id') = {plan_id}
            ORDER BY id ASC
        """
        rows = app.dln.query_relational(sql)
        
        obs_list = []
        for row in rows:
            log_data = json.loads(row[0])
            payload = log_data.get('payload', {})
            device = log_data.get('device', 'unknown').upper()
            cmd = log_data.get('command', 'unknown')
            args_used = log_data.get('args', {})
            data_vals = payload.get('data', payload)
            
            # Format cleanly: PRIMUS.read_voc({}) -> {"TVOC_ppb": 150}
            obs_list.append(f"{device}.{cmd}({args_used}) -> {json.dumps(data_vals)}")
        
        injected_observation = "\n".join(obs_list) if obs_list else "No observations recorded in this phase."

        # 2. Re-trigger the run agent
        run_handler = app.commands.get("/run")
        if not run_handler:
            raise RuntimeError("Run handler not found in app.commands.")
        
        # Invoke the handler with the AI's intent, injecting the data we just collected
        run_handler(intent, injected_observation=injected_observation)