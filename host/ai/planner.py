import json

class Planner:
    def __init__(self, world_model, command_sets, guidance_dict=None):
        self.world_model = world_model
        self.command_sets = command_sets
        self.guidance_dict = guidance_dict or {}

    def build_system_context(self):
        # Build the guidance section from all connected devices
        guidance_text = ""
        for device, text in self.guidance_dict.items():
            guidance_text += f"## {device.upper()} GUIDANCE:\n{text}\n\n"

        return f"""You are a Laboratory AI Controller. 
Your goal is to complete the user's request by issuing one command at a time.

# DEVICE OPERATIONAL GUIDANCE
{guidance_text}

# AVAILABLE COMMANDS (JSON)
{json.dumps(self.command_sets, indent=2)}

# REAGENTS
{json.dumps(self.world_model.get('reagents', {}))}

# RULES
1. Respond ONLY with a JSON object representing the NEXT step.
2. If the task is finished, respond with: {{"status": "COMPLETE", "message": "Summary of work"}}
3. Follow the DEVICE OPERATIONAL GUIDANCE strictly to avoid hardware errors.
"""

    def build_user_prompt(self, goal, plate_summary, observation=None):
        obs_section = f"\n# LATEST OBSERVATION\n{observation}" if observation else ""
        return f"# USER GOAL\n{goal}\n\n# PLATE STATE\n{plate_summary}{obs_section}\n\nNext command?"