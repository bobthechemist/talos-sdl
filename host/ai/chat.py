# host/ai/chat.py
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
    parser = argparse.ArgumentParser(description="ALIF Agentic Laboratory Cockpit")
    parser.add_argument("--provider", type=str, help="AI Provider (vertex, ollama, openai).")
    parser.add_argument("--model", type=str, help="Specific model name.")
    args = parser.parse_args()

    print(f"\n{C.OK}==========================================")
    print("      ALIF AGENTIC LABORATORY COCKPIT      ")
    print(f"=========================================={C.END}")
    
    # 1. World & Hardware Setup
    world_path = "job_world.json"
    if os.path.exists(world_path):
        world_model = load_world_from_file(world_path)
    else:
        print(f"{C.WARN}No world model found. Defaulting to generic setup.{C.END}")
        world_model = {"reagents": {"p1": "Unknown"}, "max_well_volume_ul": 250.0, "experiment_name": "Chat_Session"}

    if not check_devices_attached(): sys.exit(1)
    manager, device_ports = connect_devices()
    if not manager: sys.exit(1)

    plate_manager = PlateManager(max_volume_ul=world_model['max_well_volume_ul'])
    
    # 2. Capabilities & Planner
    full_caps = get_instructions(manager, device_ports)
    ai_commands = {}
    ai_guidance = {}
    for dev, payload in full_caps.items():
        ai_commands[dev] = {k: v for k, v in payload.get('data', {}).items() if v.get('ai_enabled', False)}
        ai_guidance[dev] = payload.get('metadata', {}).get('ai_guidance', "")

    planner = Planner(world_model, ai_commands, ai_guidance)
    
    # 3. Initialize AGENTS (Dual Contexts)
    print(f"{C.INFO}[+] Initializing AI Agents...{C.END}")
    
    # Agent for /run (Controller)
    planner.set_mode(Planner.MODE_RUN)
    run_agent = LLMManager.get_agent(provider=args.provider, model=args.model, context=planner.build_system_context())
    
    # Agent for /data (Analyst)
    planner.set_mode(Planner.MODE_DATA)
    data_agent = LLMManager.get_agent(provider=args.provider, model=args.model, context=planner.build_system_context())
    
    # Default to RUN mode
    planner.set_mode(Planner.MODE_RUN)
    current_agent = run_agent
    
    executor = AgentExecutor(
        manager=manager, 
        device_ports=device_ports, 
        agent=current_agent,  # Placeholder, swapped in loop
        planner=planner, 
        plate_manager=plate_manager
    )

    print(f"\n{C.INFO}System Online. Mode: /run (Laboratory Controller){C.END}")
    print(f"{C.INFO}Commands: /run, /data, log, clear, quit{C.END}")

    # 4. REPL Loop
    try:
        while True:
            try:
                mode_str = "RUN" if planner.current_mode == Planner.MODE_RUN else "DATA"
                prompt_color = C.WARN if mode_str == "RUN" else C.OK
                user_input = input(f"\n{prompt_color}[{mode_str}] > {C.END}").strip()
                
                if not user_input: continue
                
                # --- Slash Commands ---
                if user_input.startswith("/"):
                    cmd = user_input.split()[0].lower()
                    remainder = " ".join(user_input.split()[1:])
                    
                    if cmd == "/run":
                        planner.set_mode(Planner.MODE_RUN)
                        current_agent = run_agent
                        print(f"{C.INFO}Switched to RUN mode (Controller).{C.END}")
                        if remainder: user_input = remainder
                        else: continue
                    
                    elif cmd == "/data":
                        planner.set_mode(Planner.MODE_DATA)
                        current_agent = data_agent
                        print(f"{C.INFO}Switched to DATA mode (Analyst).{C.END}")
                        if remainder: user_input = remainder
                        else: continue
                    
                    else:
                        print(f"{C.ERR}Unknown command: {cmd}{C.END}")
                        continue

                # --- Standard Commands ---
                if user_input.lower() in ('quit', 'exit', 'q'): break
                if user_input.lower() == 'clear':
                    current_agent.clear_history()
                    print(f"{C.INFO}Current context history cleared.{C.END}")
                    continue
                if user_input.lower() == 'log':
                    executor.save_log()
                    continue

                # --- Execution ---
                # Update executor's active agent
                executor.agent = current_agent
                
                if planner.current_mode == Planner.MODE_RUN:
                    # Run the full ReAct loop
                    executor.run(user_input)
                else:
                    # Data mode just chats for now (Tools coming in M2)
                    print(f"[*] Analyzing...")
                    response = current_agent.prompt(user_input, use_history=True)
                    print(f"\n{C.OK}{response}{C.END}")

            except KeyboardInterrupt:
                print(f"\n{C.WARN}Interrupted.{C.END}")
                continue

    finally:
        print(f"\n{C.INFO}Shutting down...")
        executor.save_log()
        manager.stop()
        print(f"{C.OK}Goodbye.{C.END}")

if __name__ == "__main__":
    main()