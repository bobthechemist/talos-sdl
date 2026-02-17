# host/ai/ai_chat.py
import sys
import os
import argparse
from pathlib import Path

# Setup project root path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from host.core.device_manager import DeviceManager
from host.lab.sidekick_plate_manager import PlateManager
from host.ai.llm_manager import LLMManager
from host.ai.planner import Planner
from host.ai.agent_executor import AgentExecutor
from host.ai.ai_utils import connect_devices, check_devices_attached, get_instructions, load_world_from_file
from host.gui.console import C

def main():
    # --- 0. Parse Command Line Arguments ---
    parser = argparse.ArgumentParser(description="ALIF Agentic Laboratory Cockpit")
    parser.add_argument(
        "--provider", 
        type=str, 
        help="AI Provider to use (vertex, ollama, openai). Overrides AI_PROVIDER env var."
    )
    parser.add_argument(
        "--model", 
        type=str, 
        help="Specific model name (e.g., gemini-2.5-flash-lite, llama3). Overrides AI_MODEL env var."
    )
    args = parser.parse_args()

    print(f"\n{C.OK}==========================================")
    print("      ALIF AGENTIC LABORATORY COCKPIT      ")
    print(f"=========================================={C.END}")
    
    # 1. World Setup
    world_path = "job_world.json"
    if os.path.exists(world_path):
        world_model = load_world_from_file(world_path)
    else:
        print(f"{C.WARN}No world model found. Defaulting to generic setup.{C.END}")
        world_model = {
            "reagents": {"p1": "Unknown"},
            "max_well_volume_ul": 250.0,
            "experiment_name": "Chat_Session"
        }

    # 2. Hardware Setup
    if not check_devices_attached():
        sys.exit(1)
    
    manager, device_ports = connect_devices()
    if not manager:
        sys.exit(1)

    # 3. Logic Setup
    plate_manager = PlateManager(max_volume_ul=world_model['max_well_volume_ul'])
    
    # Fetch Capabilities & Guidance
    full_caps = get_instructions(manager, device_ports)
    ai_commands = {}
    ai_guidance = {}
    for dev, payload in full_caps.items():
        ai_commands[dev] = {k: v for k, v in payload.get('data', {}).items() if v.get('ai_enabled', False)}
        ai_guidance[dev] = payload.get('metadata', {}).get('ai_guidance', "")

    planner = Planner(world_model, ai_commands, ai_guidance)
    
    # 4. Initialize Agent
    # The agent persists for the entire session (maintaining conversation history).
    # LLMManager will handle the logic: Args > Env Vars > Defaults.
    print(f"{C.INFO}[+] Initializing AI Agent...{C.END}")
    try:
        agent = LLMManager.get_agent(
            provider=args.provider, 
            model=args.model,
            context=planner.build_system_context()
        )
        
        # Determine display name for the log
        provider_name = args.provider if args.provider else os.getenv("AI_PROVIDER", "vertex")
        model_name = getattr(agent, "model_name", "unknown model")
        print(f"{C.OK}    -> Connected to {provider_name.upper()} using {model_name}.{C.END}")

    except Exception as e:
        print(f"{C.ERR}    -> Failed to initialize agent: {e}{C.END}")
        print(f"{C.INFO}       Ensure 'openai' is installed for Ollama support (`pip install openai`).{C.END}")
        manager.stop()
        sys.exit(1)

    # The Executor handles the ReAct loops
    executor = AgentExecutor(
        manager=manager, 
        device_ports=device_ports, 
        agent=agent, 
        planner=planner, 
        plate_manager=plate_manager,
        require_confirmation=True # Set to False for fully autonomous mode
    )

    print(f"\n{C.INFO}System Online. Session is being logged to temp/.{C.END}")
    print(f"{C.INFO}Commands: 'quit' to exit, 'clear' to reset history, 'log' to save current data.{C.END}")

    # 5. The REPL Loop
    try:
        while True:
            try:
                user_input = input(f"\n{C.WARN}Human > {C.END}").strip()
                
                if not user_input: continue
                
                if user_input.lower() in ('quit', 'exit', 'q'):
                    break
                
                if user_input.lower() == 'clear':
                    agent.clear_history()
                    print(f"{C.INFO}Conversation history cleared.{C.END}")
                    continue

                if user_input.lower() == 'log':
                    executor.save_log()
                    continue

                # Run the agentic loop for this specific user goal
                executor.run(user_input)
                
            except KeyboardInterrupt:
                print(f"\n{C.WARN}Task interrupted. Control returned to human.{C.END}")
                continue

    finally:
        print(f"\n{C.INFO}Shutting down...")
        executor.save_log()
        manager.stop()
        print(f"{C.OK}Goodbye.{C.END}")

if __name__ == "__main__":
    main()