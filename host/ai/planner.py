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
Your goal is to complete the user's request by issuing ONE command at a time.

# DEVICE GUIDANCE & CONSTRAINTS
{guidance_section}

# AVAILABLE COMMANDS (JSON)
{json.dumps(self.command_sets, indent=2)}

# REAGENTS (World Model)
{json.dumps(self.world_model.get('reagents', {}), indent=2)}

# RULES
1. Respond ONLY with a JSON object representing the NEXT step.
2. Format: {{"device": "name", "command": "cmd", "args": {{...}}}}
3. If the task is finished, respond with: {{"status": "COMPLETE", "message": "Summary of work"}}
4. ALWAYS follow the specific guidance for each device to ensure safety and precision.
"""

    def build_user_prompt(self, goal, plate_summary, observation=None):
        obs_section = f"\n# LATEST OBSERVATION\n{observation}" if observation else ""
        return f"""# USER GOAL
{goal}

# CURRENT PLATE STATE
{plate_summary}
{obs_section}

What is the next command?"""