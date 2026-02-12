class BaseAgent:
    def __init__(self, context=None):
        self.context = context
        self.history = []
        self.last_run_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def prompt(self, user_prompt, use_history=True, **kwargs):
        raise NotImplementedError("Subclasses must implement prompt()")

    def clear_history(self):
        self.history = []
        self.last_run_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}