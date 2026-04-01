# host/ai/planner.py
import json

class Planner:
    MODE_RUN = "run"
    MODE_DATA = "data"

    def __init__(self, world_model, command_sets, guidance_dict=None):
        self.world_model = world_model
        self.command_sets = command_sets
        self.guidance_dict = guidance_dict or {}
        self.current_mode = self.MODE_RUN

    def set_mode(self, mode):
        if mode not in [self.MODE_RUN, self.MODE_DATA]: raise ValueError(f"Invalid mode: {mode}")
        self.current_mode = mode

    def build_system_context(self):
        if self.current_mode == self.MODE_RUN: return self._build_run_context()
        else: return self._build_data_context()

    def _build_run_context(self):
        guidance_section = ""
        for device, text in self.guidance_dict.items():
            if text: guidance_section += f"### {device.upper()} OPERATIONAL GUIDANCE:\n{text}\n\n"

        return f"""You are an expert Laboratory AI Controller (RUN MODE).
Your goal is to translate the user's natural language request into a sequence of hardware commands.

# DEVICE GUIDANCE & CONSTRAINTS
{guidance_section}

# AVAILABLE COMMANDS (JSON)
{json.dumps(self.command_sets, indent=2)}

# REAGENTS (World Model)
{json.dumps(self.world_model.get('reagents', {}), indent=2)}

# RESPONSE FORMAT RULES
1. Respond ONLY with a JSON object.
2. The JSON object must contain a key "plan" which is a LIST of command objects.
3. Each command object must have: "device", "command", and "args".
4. If the task is finished or no action is needed, return: {{"status": "COMPLETE", "message": "..."}}
"""

    def _build_data_context(self):
        reagents = json.dumps(self.world_model.get('reagents', {}), indent=2)
        return f"""You are a Laboratory Data Analyst (DATA MODE).
Your goal is to help the user understand experimental data.

# CURRENT SESSION REAGENTS
{reagents}

# CAPABILITIES
1. You CANNOT control hardware.
2. You have access to:
   - "HISTORICAL SUMMARIES": Brief linguistic records of what happened in the past.
   - "DATASET RECORDS": Raw instrument data retrieved based on your current query.

# INSTRUCTIONS
- Respond in clear natural language.
- Use the reagent mapping to translate device IDs (like 'p1') into chemical names.
"""

    def build_user_prompt(self, goal, plate_summary=None, observation=None):
        """This was the missing method in the error trace."""
        if self.current_mode == self.MODE_RUN:
            obs_section = f"\n# PREVIOUS EXECUTION RESULT\n{observation}" if observation else ""
            return f"# USER GOAL\n{goal}\n{obs_section}\n\nGenerate the execution plan."
        else:
            return goal