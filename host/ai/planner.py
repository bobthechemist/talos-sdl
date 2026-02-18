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
        if mode not in [self.MODE_RUN, self.MODE_DATA]:
            raise ValueError(f"Invalid mode: {mode}")
        self.current_mode = mode

    def build_system_context(self):
        if self.current_mode == self.MODE_RUN:
            return self._build_run_context()
        else:
            return self._build_data_context()

    def _build_run_context(self):
        # Format the guidance strings for the prompt
        guidance_section = ""
        for device, text in self.guidance_dict.items():
            if text:
                guidance_section += f"### {device.upper()} OPERATIONAL GUIDANCE:\n{text}\n\n"

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

Example Response:
{{
  "plan": [
    {{"device": "sidekick", "command": "home", "args": {{}}}},
    {{"device": "sidekick", "command": "move_to", "args": {{"x": 10, "y": 5}}}}
  ]
}}
"""

    def _build_data_context(self):
        return """You are a Laboratory Data Analyst (DATA MODE).
Your goal is to help the user understand the data collected during experiments.

# CONSTRAINTS
1. You CANNOT control hardware. You cannot issue commands like 'move' or 'dispense'.
2. You can analyze datasets, summarize findings, and answer questions about chemistry.
3. Respond in natural language (Markdown is supported).

# AVAILABLE TOOLS
- list_datasets(): Shows available data files.
- summarize(id): Gets statistics for a dataset.
- plot(id, columns): Creates a visualization.

(Note: Tools will be executed by the host when you call them using the format: Tool: func_name(args))
"""

    def build_user_prompt(self, goal, plate_summary, observation=None):
        if self.current_mode == self.MODE_RUN:
            obs_section = f"\n# PREVIOUS EXECUTION RESULT\n{observation}" if observation else ""
            return f"""# USER GOAL
{goal}

# CURRENT PLATE STATE
{plate_summary}
{obs_section}

Generate the execution plan."""
        else:
            # Data mode prompt is simpler, focusing on the conversation
            return goal