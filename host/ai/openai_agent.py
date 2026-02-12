import os
from openai import OpenAI
from .base_agent import BaseAgent

class OpenAIAgent(BaseAgent):
    """Implementation for OpenAI-compatible APIs (Ollama, Groq, OpenAI)."""
    
    def __init__(self, context=None, model_name="llama3", base_url="http://localhost:11434/v1"):
        BaseAgent.__init__(self, context)
        self.model_name = model_name
        self.client = OpenAI(
            base_url=base_url,
            api_key=os.getenv("OPENAI_API_KEY", "ollama") 
        )

    def prompt(self, user_prompt, use_history=True, **kwargs):
        try:
            messages = []
            if self.context:
                messages.append({"role": "system", "content": self.context})
            
            if use_history:
                messages.extend(self.history)
            
            messages.append({"role": "user", "content": user_prompt})

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                **kwargs
            )

            usage = response.usage
            self.last_run_info = {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            }

            response_text = response.choices[0].message.content

            if use_history:
                self.history.append({"role": "user", "content": user_prompt})
                self.history.append({"role": "assistant", "content": response_text})

            return response_text

        except Exception as e:
            print("[OpenAIAgent Error]: " + str(e))
            return None