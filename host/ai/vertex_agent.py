# host/ai/vertex_agent.py
import os
import time
from google import genai
from google.genai import types
from .base_agent import BaseAgent

class VertexAgent(BaseAgent):
    """Implementation for Google Vertex AI / Gemini with Exponential Backoff."""
    
    def __init__(self, context=None, model_name="gemini-2.5-flash-lite"):
        BaseAgent.__init__(self, context)
        self.model_name = model_name
        self.client = genai.Client(
            vertexai=True,
            project=os.getenv("GC_PROJECT_ID"),
            location=os.getenv("GC_LOCATION", "us-east4"),
        )

    def prompt(self, user_prompt, use_history=True, **kwargs):
        # Reset turn info at the start of every prompt call
        self.last_run_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        # --- Backoff Configuration ---
        max_retries = 5
        base_delay = 2  # Start with 2 seconds
        attempt = 0

        while attempt <= max_retries:
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
                error_str = str(e).lower()
                # Check for 429 (Too Many Requests) or ResourceExhausted errors
                if "429" in error_str or "resourceexhausted" in error_str or "quota" in error_str:
                    attempt += 1
                    if attempt > max_retries:
                        print(f"[VertexAgent Error] Max retries ({max_retries}) exceeded for rate limit: {e}")
                        return None
                    
                    # Calculate sleep time: 2s, 4s, 8s, 16s...
                    sleep_time = base_delay * (2 ** (attempt - 1))
                    print(f"[VertexAgent] Rate Limit Hit (429). Retrying in {sleep_time}s... (Attempt {attempt}/{max_retries})")
                    time.sleep(sleep_time)
                    continue
                else:
                    # If it's not a rate limit error (e.g., Auth error, Bad Request), fail immediately
                    print(f"[VertexAgent Error]: {type(e).__name__}: {e}")
                    return None