class BaseAgent:
    """
    Base class for all LLM providers (The 'Base Postman').
    Uses NotImplementedError instead of abc for hardware compatibility.
    """
    
    def __init__(self, context=None):
        self.context = context
        self.history = []

    def prompt(self, user_prompt, use_history=True, **kwargs):
        """Sends a prompt to the LLM and returns the text response."""
        raise NotImplementedError("Subclasses must implement prompt()")

    def clear_history(self):
        """Clears the conversation history."""
        self.history = []