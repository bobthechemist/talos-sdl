# host/ai/prompt_factory.py
import json

class PromptFactory:
    """
    A factory responsible for constructing system and user prompts for the AI
    based on the current mode and available information.
    """
    def __init__(self, world_model, command_sets, guidance_dict=None):
        self.world_model = world_model
        self.command_sets = command_sets
        self.guidance_dict = guidance_dict or {}

    def get_system_prompt(self, mode: str):
        """Returns the appropriate system prompt based on the mode."""
        if mode == "run":
            return self._build_run_system_prompt()
        elif mode == "data":
            return self._build_data_system_prompt()
        else:
            raise ValueError(f"Invalid mode for system prompt: {mode}")

    def _build_run_system_prompt(self):
        guidance = "\n".join(f"### {dev.upper()} GUIDANCE:\n{text}" for dev, text in self.guidance_dict.items() if text)
        return f"""You are an expert Laboratory AI Controller (RUN MODE).
Your goal is to translate the user's request into a sequence of hardware commands.

# DEVICE GUIDANCE & CONSTRAINTS
{guidance}

# AVAILABLE COMMANDS (JSON)
{json.dumps(self.command_sets, indent=2)}

# REAGENTS (World Model)
{json.dumps(self.world_model.get('reagents', {}), indent=2)}

# RESPONSE FORMAT
- Respond ONLY with a single JSON object.
- The object must have a "plan" key containing a LIST of command objects.
- Each command object must have "device", "command", and "args" keys.
- If the task is finished, return: {{"plan": [], "status": "COMPLETE", "message": "..."}}
"""

    def _build_data_system_prompt(self):
        reagents = json.dumps(self.world_model.get('reagents', {}), indent=2)
        return f"""You are a Laboratory Data Analyst (DATA MODE).
Your goal is to answer user questions by interpreting experimental data provided in the context.

# CURRENT SESSION REAGENTS
{reagents}

# YOUR CAPABILITIES
- You CANNOT control hardware.
- You will be given context from a Digital Lab Notebook (DLN).
- This context includes high-level summaries and raw JSON data from instruments.

# INSTRUCTIONS
- Respond in clear, natural language using Markdown for formatting.
- If you are provided with raw JSON data (e.g., from an 'observation' log), you MUST use it to answer the user's question.
- When asked for "raw data", format the relevant JSON data into a clear Markdown table.
- Synthesize information from all provided context sections to give a complete answer.

# ROLE CONSTRAINTS
- You are not to engage in social responses or provide information outside of the experimental data context.
- Do not provide unrelated creative writing or general knowledge answers.
"""

    def build_run_user_prompt(self, goal, observation=None):
        obs_section = f"\n# PREVIOUS EXECUTION RESULT\n{observation}" if observation else ""
        return f"# USER GOAL\n{goal}{obs_section}\n\nGenerate the execution plan."