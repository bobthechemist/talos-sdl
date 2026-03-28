import os
from dotenv import load_dotenv
from .vertex_agent import VertexAgent
from .openai_agent import OpenAIAgent
from .gemini_agent import GeminiAgent

load_dotenv()

class LLMManager:
    """The central manager to swap between AI providers."""
    
    @staticmethod
    def get_agent(provider=None, context=None, model=None):
        """
        Factory method to return the configured agent.
        Provider defaults to .env variable 'AI_PROVIDER'
        """
        provider = provider or os.getenv("AI_PROVIDER", "gemini").lower()
        
        if provider == "vertex":
            model = model or os.getenv("AI_MODEL", "gemini-2.5-flash-lite")
            return VertexAgent(context=context, model_name=model)
            
        elif provider == "ollama":
            model = model or os.getenv("AI_MODEL", "llama3.1")
            url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
            # Request the 32k context window here
            ollama_config = {"num_ctx": 32768}

            return OpenAIAgent(context=context, model_name=model, base_url=url,model_kwargs=ollama_config)

        elif provider == "gemini":
            # Google AI Studio (requires API Key)
            model = model or os.getenv("AI_MODEL", "gemini-2.5-flash-lite")
            return GeminiAgent(context=context, model_name=model)
                
        elif provider == "openai":
            model = model or os.getenv("AI_MODEL", "gpt-4o")
            return OpenAIAgent(context=context, model_name=model, base_url="https://api.openai.com/v1")
            
        else:
            raise ValueError(f"Unknown AI Provider: {provider}")

# Example Usage:
if __name__ == "__main__":
    # Test Stage 1 Success Condition:
    print("--- Testing LLM Abstraction ---")
    
    ctx = "You are a helpful laboratory assistant."
    
    # 1. Test Vertex (Gemini)
    try:
        agent_v = LLMManager.get_agent(provider="vertex", context=ctx)
        print(f"Vertex Response: {agent_v.prompt('Hello!', use_history=False)}")
    except Exception as e:
        print(f"Vertex failed/not configured: {e}")

    # 2. Test Ollama (Local)
    try:
        agent_o = LLMManager.get_agent(provider="ollama", context=ctx)
        print(f"Ollama Response: {agent_o.prompt('Hello!', use_history=False)}")
    except Exception as e:
        print(f"Ollama failed/not running: {e}")