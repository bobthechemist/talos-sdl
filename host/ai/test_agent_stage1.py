import os
import sys
from pathlib import Path

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from host.ai.llm_manager import LLMManager
from host.gui.console import C

def test_vertex_access():
    print(f"{C.INFO}=== Stage 1: LLM Abstraction Test (Vertex) ==={C.END}")
    
    # 1. Initialize the Manager with a specific context
    context = "You are a laboratory robot named ALIF. You are helpful and concise."
    
    try:
        print(f"[*] Instantiating VertexAgent via LLMManager...")
        agent = LLMManager.get_agent(provider="vertex", context=context)
        
        # 2. Test Turn 1 (Stateless check)
        print(f"[*] Turn 1: Asking for identity...")
        response1 = agent.prompt("What is your name and what do you do?", use_history=True)
        
        if response1:
            print(f"{C.OK}    Response: {response1.strip()}{C.END}")
        else:
            print(f"{C.ERR}    Failed to get a response from Turn 1.{C.END}")
            return

        # 3. Test Turn 2 (History/Context check)
        print(f"[*] Turn 2: Testing memory...")
        response2 = agent.prompt("I just asked you your name. Do you remember what I called you?", use_history=True)
        
        if response2 and "ALIF" in response2.upper():
            print(f"{C.OK}    Response: {response2.strip()}{C.END}")
            print(f"\n{C.OK}SUCCESS: VertexAgent is accessible and maintains history.{C.END}")
        else:
            print(f"{C.WARN}    Response: {response2.strip()}{C.END}")
            print(f"{C.ERR}FAILURE: Response received, but context/history may be missing.{C.END}")

    except Exception as e:
        print(f"{C.ERR}An error occurred during Stage 1 testing: {e}{C.END}")
        print(f"{C.INFO}Check your .env for GC_PROJECT_ID and GC_LOCATION.{C.END}")

if __name__ == "__main__":
    test_vertex_access()