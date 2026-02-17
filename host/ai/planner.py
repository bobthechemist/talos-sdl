# host/ai/planner.py
import json

class Planner:
    def __init__(self, world_model, command_sets, guidance_dict=None):
        self.world_model = world_model
        self.command_sets = command_sets
        self.guidance_dict = guidance_dict or {}

    def build_system_context(self):
        # Format the guidance strings for the prompt
        guidance_section = ""
        for device, text in self.guidance_dict.items():
            if text:
                guidance_section += f"### {device.upper()} OPERATIONAL GUIDANCE:\n{text}\n\n"

        return f"""You are an expert Laboratory AI Controller.
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

Example Response:
{{
  "plan": [
    {{"device": "sidekick", "command": "home", "args": {{}}}},
    {{"device": "sidekick", "command": "move_to", "args": {{"x": 10, "y": 5}}}}
  ]
}}
"""

    def build_user_prompt(self, goal, plate_summary, observation=None):
        obs_section = f"\n# PREVIOUS EXECUTION RESULT\n{observation}" if observation else ""
        return f"""# USER GOAL
{goal}

# CURRENT PLATE STATE
{plate_summary}
{obs_section}

Generate the execution plan."""