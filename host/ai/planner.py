# host/ai/planner.py
import json

class Planner:
    MODE_RUN = "run"
    MODE_DATA = "data"

    def __init__(self, world_model, command_sets, guidance_dict=None):
        self.world_model = world_model
        self.command_sets = command_sets
        # Add virtual DLN commands to the set
        self.command_sets["dln"] = {
            "save_protocol": {
                "description": "Saves a sequence of commands as a named protocol for later reuse.",
                "args": [
                    {"name": "name", "type": "str", "description": "Unique name for the protocol."},
                    {"name": "description", "type": "str", "description": "Brief description of what this procedure does."},
                    {"name": "plan", "type": "list", "description": "The list of command objects to save."}
                ],
                "ai_enabled": True
            },
            "execute_protocol": {
                "description": "Loads and executes a previously saved named protocol.",
                "args": [
                    {"name": "name", "type": "str", "description": "The name of the protocol to load."}
                ],
                "ai_enabled": True
            },
            "list_protocols": {
                "description": "Returns a list of all protocols stored in the lab notebook.",
                "args": [],
                "ai_enabled": True
            }
        }
        self.guidance_dict = guidance_dict or {}
        self.current_mode = self.MODE_RUN

    # [Keep existing set_mode and build_system_context methods...]

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

# DIGITAL LAB NOTEBOOK (DLN) MEMORY
You can save successful plans as 'protocols' using the 'dln' device. 
- Use 'save_protocol' ONLY after a procedure has been proven to work or when explicitly asked.
- Use 'execute_protocol' to repeat complex tasks without re-planning every step.

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
        return """You are a Laboratory Data Analyst (DATA MODE).
Your goal is to help the user understand experimental data.

# CAPABILITIES
1. You CANNOT control hardware.
2. You can discuss chemistry, analyze results, and answer questions.
3.  **HISTORICAL RECORDS**: The system automatically retrieves relevant past experiments based on the user's query and injects them under the header "=== RELEVANT HISTORICAL RECORDS ===". Use this to answer questions about the past. 

# INSTRUCTIONS
- Respond in clear natural language.
- Analyze the provided JSON data to answer the user's questions.
"""

    def build_user_prompt(self, goal, plate_summary, current_well="Unknown", observation=None):
        if self.current_mode == self.MODE_RUN:
            obs_section = f"\n# PREVIOUS EXECUTION RESULT (Read carefully if this is an error)\n{observation}" if observation else ""
            return f"""# USER GOAL
{goal}


Generate the execution plan."""
        else:
            return goal