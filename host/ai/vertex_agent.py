import os
from google import genai
from google.genai import types
from .base_agent import BaseAgent

class VertexAgent(BaseAgent):
    """Implementation for Google Vertex AI / Gemini."""
    
    def __init__(self, context=None, model_name="gemini-2.0-flash"):
        # Explicit call to super() init for CP-style compatibility
        BaseAgent.__init__(self, context)
        self.model_name = model_name
        self.client = genai.Client(
            vertexai=True,
            project=os.getenv("GC_PROJECT_ID"),
            location=os.getenv("GC_LOCATION", "us-east4"),
        )

    def prompt(self, user_prompt, use_history=True, **kwargs):
        try:
            contents = []
            if use_history:
                contents.extend(self.history)
            
            contents.append(types.Content(role="user", parts=[types.Part(text=user_prompt)]))

            config = types.GenerateContentConfig(
                system_instruction=self.context,
                **kwargs,
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )

            if not response.candidates:
                return None

            response_text = response.candidates[0].content.parts[0].text

            if use_history:
                self.history.append(types.Content(role="user", parts=[types.Part(text=user_prompt)]))
                self.history.append(types.Content(role="model", parts=[types.Part(text=response_text)]))

            return response_text

        except Exception as e:
            print("[VertexAgent Error]: " + str(e))
            return None