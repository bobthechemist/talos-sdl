# host/ai/vertex_agent.py
import os
from google import genai
from google.genai import types
from .base_agent import BaseAgent

class VertexAgent(BaseAgent):
    """Implementation for Google Vertex AI / Gemini."""
    
    def __init__(self, context=None, model_name="gemini-2.5-flash-lite"):
        BaseAgent.__init__(self, context)
        self.model_name = model_name
        self.client = genai.Client(
            vertexai=True,
            project=os.getenv("GC_PROJECT_ID"),
            location=os.getenv("GC_LOCATION", "us-east4"),
        )

    def prompt(self, user_prompt, use_history=True, **kwargs):
        # Reset turn info at the start of every prompt
        self.last_run_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        try:
            contents = []
            if use_history:
                contents.extend(self.history)
            
            contents.append(types.Content(role="user", parts=[types.Part(text=user_prompt)]))

            config = types.GenerateContentConfig(
                system_instruction=self.context,
                **kwargs,
            )

            # --- API CALL ---
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

            # --- CAPTURE METADATA ---
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = response.usage_metadata
                self.last_run_info = {
                    "prompt_tokens": usage.prompt_token_count or 0,
                    "completion_tokens": usage.candidates_token_count or 0,
                    "total_tokens": usage.total_token_count or 0
                }

            if not response.candidates or not response.candidates[0].content.parts:
                print("[VertexAgent Warning]: No response text returned by model.")
                return None

            response_text = response.candidates[0].content.parts[0].text

            if use_history:
                self.history.append(types.Content(role="user", parts=[types.Part(text=user_prompt)]))
                self.history.append(types.Content(role="model", parts=[types.Part(text=response_text)]))

            return response_text

        except Exception as e:
            # Re-wrap error message to be descriptive
            print(f"[VertexAgent Error]: {type(e).__name__}: {e}")
            return None