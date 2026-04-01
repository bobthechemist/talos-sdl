# host/ai/chat.py
import sys
import os
import argparse
import re
import json
from pathlib import Path

# Setup project root path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from host.core.device_manager import DeviceManager
from host.lab.sidekick_plate_manager import PlateManager
from host.ai.llm_manager import LLMManager
from host.ai.planner import Planner
from host.ai.agent_executor import AgentExecutor
from host.ai.ai_utils import connect_devices, get_instructions, load_world_from_file
from host.gui.console import C
from host.dln.session_manager import SessionManager

def print_help():
    print(f"\n{C.INFO}--- Available Commands ---{C.END}")
    print(f"  {C.OK}/run [goal]{C.END}    : Switch to Controller Mode (or execute a goal).")
    print(f"  {C.OK}/data [query]{C.END}  : Switch to Analyst Mode (or ask a question).")
    print(f"  {C.OK}/confirm [on|off]{C.END}: Toggle human confirmation before hardware execution.")
    print(f"  {C.OK}/datasets{C.END}      : List all recorded datasets in this notebook.")
    print(f"  {C.OK}/clear{C.END}         : Clear the AI's short-term context.")
    print(f"  {C.OK}/quit{C.END}          : Exit the application and save session.")

def main():
    parser = argparse.ArgumentParser(description="ALIF Agentic Laboratory Cockpit")
    parser.add_argument("--provider", type=str, help="AI Provider (gemini, ollama, openai).")
    parser.add_argument("--model", type=str, help="Specific model name.")
    args = parser.parse_args()

    print(f"\n{C.OK}==========================================")
    print("      ALIF AGENTIC LABORATORY COCKPIT      ")
    print(f"=========================================={C.END}")
    
    # 1. World Model Setup
    world_path = "job_world.json"
    if os.path.exists(world_path):
        world_model = load_world_from_file(world_path)
    else:
        print(f"{C.WARN}No world model found. Defaulting to generic setup.{C.END}")
        world_model = {
            "reagents": {"p1": "reagent 1", "p2": "reagent 2", "p3": "reagent 3", "p4": "reagent 4"},
            "max_well_volume_ul": 250.0, 
            "experiment_name": "General Experiment"
        }

    # 2. Initialize Digital Lab Notebook
    print(f"{C.INFO}[+] Initializing Digital Lab Notebook...{C.END}")
    session_manager = SessionManager(base_dir=".talos")
    session_manager.start_session(
        world_model=world_model,
        title=world_model.get('experiment_name'),
        objective="Agentic session started via Laboratory Cockpit"
    )

    # 3. Hardware Setup (Decoupled)
    manager, device_ports = connect_devices()
    
    # 4. Capabilities Discovery (Dynamic)
    full_caps = get_instructions(manager, device_ports)
    ai_commands = {}
    ai_guidance = {}
    
    if full_caps:
        for dev, payload in full_caps.items():
            # Filter for commands the AI is allowed to use
            ai_commands[dev] = {k: v for k, v in payload.get('data', {}).items() if v.get('ai_enabled', False)}
            # Capture instrument-specific guidance for the prompt
            ai_guidance[dev] = payload.get('metadata', {}).get('ai_guidance', "")
    else:
        print(f"{C.WARN}No instrument capabilities discovered. AI will operate with restricted tools.{C.END}")

    # Initialize state managers
    plate_manager = PlateManager(max_volume_ul=world_model.get('max_well_volume_ul', 250))
    planner = Planner(world_model, ai_commands, ai_guidance)
    
    # 5. Agent Initialization
    print(f"{C.INFO}[+] Initializing AI Agents (Dual Contexts)...{C.END}")
    
    # Setup the Controller (Run) Agent
    planner.set_mode(Planner.MODE_RUN)
    run_agent = LLMManager.get_agent(provider=args.provider, model=args.model, context=planner.build_system_context())
    
    # Setup the Analyst (Data) Agent
    planner.set_mode(Planner.MODE_DATA)
    data_agent = LLMManager.get_agent(provider=args.provider, model=args.model, context=planner.build_system_context())
    
    # Default to Run mode
    planner.set_mode(Planner.MODE_RUN)
    current_agent = run_agent
    
    executor = AgentExecutor(
        manager=manager, 
        device_ports=device_ports, 
        agent=current_agent,
        planner=planner, 
        plate_manager=plate_manager,
        session_manager=session_manager,
        require_confirmation=True 
    )

    print(f"\n{C.INFO}System Online. Notebook Session: {session_manager.current_exp_id}{C.END}")
    print(f"{C.INFO}Type /help for a list of commands.{C.END}")

    # 6. REPL Loop
    try:
        while True:
            try:
                mode_str = "RUN" if planner.current_mode == Planner.MODE_RUN else "DATA"
                prompt_color = C.WARN if mode_str == "RUN" else C.OK
                safety_char = "🔒" if executor.require_confirmation else "⚡"
                
                user_input = input(f"\n{prompt_color}[{mode_str} {safety_char}] > {C.END}").strip()
                if not user_input: continue
                
                # --- Slash Commands ---
                if user_input.startswith("/"):
                    parts = user_input.split()
                    cmd = parts[0].lower()
                    remainder = " ".join(parts[1:])
                    
                    if cmd in ("/quit", "/exit"): break
                    
                    elif cmd == "/help":
                        print_help()
                        continue

                    elif cmd == "/clear":
                        current_agent.clear_history()
                        print(f"{C.INFO}Context cleared for {mode_str}.{C.END}")
                        continue

                    elif cmd == "/confirm":
                        executor.require_confirmation = not ("off" in remainder.lower())
                        status = "OFF ⚡" if not executor.require_confirmation else "ON 🔒"
                        print(f"{C.INFO}Safety Gate: {status}{C.END}")
                        continue

                    elif cmd == "/datasets":
                        # Query StorageManager via SessionManager to list entries in the notebook
                        session = session_manager.storage.Session()
                        from host.dln.storage_manager import Attachment
                        attachments = session.query(Attachment).all()
                        print(f"\n{C.INFO}--- Lab Notebook: Registered Datasets ---{C.END}")
                        if not attachments:
                            print("No data recorded yet.")
                        for att in attachments:
                            print(f"ID: {C.OK}{att.id}{C.END} | Type: {att.data_type} | File: {att.filename}")
                        session.close()
                        continue

                    elif cmd == "/run":
                        planner.set_mode(Planner.MODE_RUN)
                        current_agent = run_agent
                        print(f"{C.INFO}Switched to RUN (Controller).{C.END}")
                        if remainder: user_input = remainder
                        else: continue
                    
                    elif cmd == "/data":
                        planner.set_mode(Planner.MODE_DATA)
                        current_agent = data_agent
                        print(f"{C.INFO}Switched to DATA (Analyst).{C.END}")
                        if remainder: user_input = remainder
                        else: continue
                    
                    else:
                        print(f"{C.ERR}Unknown command: {cmd}{C.END}")
                        continue

                # --- Execution Logic ---
                executor.agent = current_agent
                
                if planner.current_mode == Planner.MODE_RUN:
                    executor.run(user_input)


                # DATA PORTION OF LOOP
                elif planner.current_mode == Planner.MODE_DATA:
                    print(f"[*] Querying Digital Lab Notebook records...")
                    injected_context = ""

                    # 1. Semantic search for high-level summaries
                    mem_results = session_manager.search_memory(user_input, n_results=3)
                    if mem_results:
                        injected_context += "\n=== HISTORICAL SUMMARIES ===\n"
                        for res in mem_results:
                            injected_context += f"- {res['content']}\n"

                    # 2. Coordinate scanning (e.g., G9)
                    coords = re.findall(r"\b([A-H](?:1[0-2]|[1-9]))\b", user_input.upper())
                    if coords:
                        from host.dln.storage_manager import Attachment, Experiment
                        session = session_manager.storage.Session()
                        for coord in coords:
                            # Query the JSON column context_tags
                            attachments = session.query(Attachment).filter(
                                Attachment.context_tags.contains(coord)
                            ).all()
                            for att in attachments:
                                exp = session.query(Experiment).filter_by(id=att.experiment_id).first()
                                mapping = exp.world_model.get('reagents', {}) if exp and exp.world_model else {}
                                if os.path.exists(att.file_path):
                                    with open(att.file_path, 'r') as f:
                                        injected_context += f"\n=== DATASET FROM {coord} (Session: {att.experiment_id}) ===\n"
                                        injected_context += f"Reagent Mapping: {json.dumps(mapping)}\n"
                                        injected_context += f"Data: {f.read()}\n"
                        session.close()

                    # 3. Final Assembly
                    final_prompt = f"{injected_context}\n\nUSER QUESTION: {user_input}"
                    print(f"[*] Analyzing...")
                    response = current_agent.prompt(final_prompt, use_history=True)
                    print(f"\n{C.OK}{response}{C.END}")

            except KeyboardInterrupt:
                print(f"\n{C.WARN}Interrupted.{C.END}")
                continue

    finally:
        print(f"\n{C.INFO}Shutting down...")
        session_manager.end_session(summary="User exited Cockpit.")
        manager.stop()
        print(f"{C.OK}Goodbye.{C.END}")

if __name__ == "__main__":
    main()