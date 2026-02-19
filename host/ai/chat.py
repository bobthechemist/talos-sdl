# host/ai/chat.py
import sys
import os
import argparse
import re
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
from host.core.registry import Registry

def print_help():
    print(f"\n{C.INFO}--- Available Commands ---{C.END}")
    print(f"  {C.OK}/run [goal]{C.END}    : Switch to Controller Mode (or execute a goal).")
    print(f"  {C.OK}/data [query]{C.END}  : Switch to Analyst Mode (or ask a question).")
    print(f"  {C.OK}/confirm [on|off]{C.END}: Toggle human confirmation before hardware execution.")
    print(f"  {C.OK}/datasets{C.END}      : List all recorded datasets.")
    print(f"  {C.OK}/log{C.END}           : Save the current session log to disk.")
    print(f"  {C.OK}/clear{C.END}         : Clear the AI's conversation history.")
    print(f"  {C.OK}/quit{C.END}          : Exit the application.")

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
        world_model = {"reagents":
                       {"p1": "Unknown 1", 
                        "p2": "Unknown 2",
                        "p3": "Unknown 3",
                        "p4": "Unknown 4"},
                        "waste": {"x": 5, "y": -5.3},
                         "max_well_volume_ul": 250.0, 
                         "experiment_name": "Chat_Session"}

    if not check_devices_attached(): sys.exit(1)
    manager, device_ports = connect_devices()
    if not manager: sys.exit(1)

    plate_manager = PlateManager(max_volume_ul=world_model['max_well_volume_ul'])
    registry = Registry()
    
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
    
    planner.set_mode(Planner.MODE_RUN)
    run_agent = LLMManager.get_agent(provider=args.provider, model=args.model, context=planner.build_system_context())
    
    planner.set_mode(Planner.MODE_DATA)
    data_agent = LLMManager.get_agent(provider=args.provider, model=args.model, context=planner.build_system_context())
    
    # Default to RUN mode
    planner.set_mode(Planner.MODE_RUN)
    current_agent = run_agent
    
    executor = AgentExecutor(
        manager=manager, 
        device_ports=device_ports, 
        agent=current_agent,
        planner=planner, 
        plate_manager=plate_manager,
        require_confirmation=True 
    )

    print(f"\n{C.INFO}System Online. Mode: /run (Laboratory Controller){C.END}")
    print(f"{C.INFO}Type /help for a list of commands.{C.END}")

    # 4. REPL Loop
    try:
        while True:
            try:
                mode_str = "RUN" if planner.current_mode == Planner.MODE_RUN else "DATA"
                prompt_color = C.WARN if mode_str == "RUN" else C.OK
                
                safety_char = "🔒" if executor.require_confirmation else "⚡"
                
                user_input = input(f"\n{prompt_color}[{mode_str} {safety_char}] > {C.END}").strip()
                
                if not user_input: continue
                
                # --- Slash Command Handling ---
                if user_input.startswith("/"):
                    parts = user_input.split()
                    cmd = parts[0].lower()
                    remainder = " ".join(parts[1:])
                    
                    if cmd in ("/quit", "/exit"):
                        break
                    
                    elif cmd == "/help":
                        print_help()
                        continue

                    elif cmd == "/clear":
                        current_agent.clear_history()
                        print(f"{C.INFO}Conversation history cleared for {mode_str} mode.{C.END}")
                        continue

                    elif cmd == "/log":
                        executor.save_log()
                        continue

                    elif cmd == "/confirm":
                        if "off" in remainder.lower():
                            executor.require_confirmation = False
                            print(f"{C.WARN}⚠️ Safety OFF. Plans will execute immediately.{C.END}")
                        else:
                            executor.require_confirmation = True
                            print(f"{C.OK}🔒 Safety ON. Plans require confirmation.{C.END}")
                        continue

                    elif cmd == "/datasets":
                        datasets = registry.list_datasets()
                        print(f"\n{C.INFO}--- Registered Datasets ---{C.END}")
                        if not datasets:
                            print("No datasets recorded yet.")
                        else:
                            for ds in datasets:
                                print(f"ID: {C.OK}{ds['id']}{C.END} | Dev: {ds['origin_device']} | Time: {ds['timestamp']}")
                                print(f"   Files: {ds['files']}")
                        continue

                    elif cmd == "/run":
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
                        print(f"{C.ERR}Unknown command: {cmd}. Type /help for options.{C.END}")
                        continue

                # --- Execution ---
                executor.agent = current_agent
                
                if planner.current_mode == Planner.MODE_RUN:
                    executor.run(user_input)
                else:
                    # Data Mode: Check for dataset references and inject content
                    print(f"[*] Analyzing...")
                    
                    # Regex to find IDs like ds_20260218_130448
                    found_ids = re.findall(r"(ds_\d{8}_\d{6})", user_input)
                    injected_context = ""
                    
                    if found_ids:
                        print(f"{C.INFO}    -> Found dataset references: {found_ids}{C.END}")
                        for ds_id in found_ids:
                            content = registry.get_dataset_content(ds_id)
                            if content:
                                injected_context += f"\n--- DATASET {ds_id} CONTENT ---\n{content}\n"
                                print(f"{C.OK}    -> Loaded content for {ds_id}{C.END}")
                            else:
                                print(f"{C.ERR}    -> Could not load {ds_id}{C.END}")
                    
                    # Construct the final prompt for the agent
                    final_prompt = user_input
                    if injected_context:
                        final_prompt = f"{injected_context}\n\nUSER QUESTION: {user_input}"
                    
                    response = current_agent.prompt(final_prompt, use_history=True)
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