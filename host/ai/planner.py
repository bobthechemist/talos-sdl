# host/ai/planner.py
import json

class Planner:
    def __init__(self, world_model, command_sets):
        self.world_model = world_model
        self.command_sets = command_sets

    def build_system_context(self):
        return f"""You are a Laboratory AI Controller. You operate a Sidekick (pumps/arm) and a Colorimeter.
Your goal is to complete the user's request by issuing one command at a time.

# AVAILABLE COMMANDS
{json.dumps(self.command_sets, indent=2)}

# REAGENTS (World Model)
{json.dumps(self.world_model.get('reagents', {}), indent=2)}

# RULES
1. Respond ONLY with a JSON object representing the NEXT step.
2. Format: {{"device": "name", "command": "cmd", "args": {{...}}}}
3. If the task is finished, respond with: {{"status": "COMPLETE", "message": "Summary of work"}}
4. If a command fails (Observation: PROBLEM), try to fix it or explain why you can't.
"""

    def build_user_prompt(self, goal, plate_summary, observation=None):
        obs_section = f"\n# LATEST OBSERVATION\n{observation}" if observation else ""
        return f"""# USER GOAL
{goal}

# CURRENT PLATE STATE
{plate_summary}
{obs_section}

What is the next command?"""