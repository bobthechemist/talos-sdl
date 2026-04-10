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
from dln import DigitalLabNotebook, ExperimentFinalizedError # New DLN imports, including new exception


# Global variable to track the active session for data queries
active_data_query_session_id = None # Will be initialized in main()

def print_help():
    print(f"\n{C.INFO}--- Available Commands ---{C.END}")
    print(f"  {C.OK}/run [goal]{C.END}    : Switch to Controller Mode (or execute a goal).")
    print(f"  {C.OK}/data [query]{C.END}  : Switch to Analyst Mode (or ask a question about the active data session).")
    print(f"  {C.OK}/data all [query]{C.END} : Ask a question about all past experiments.")
    print(f"  {C.OK}/session{C.END}       : Show current data query session and list all available sessions.")
    print(f"  {C.OK}/session set <id>{C.END}: Switch the active data query session to <id>.")
    print(f"  {C.OK}/session rename <new_title>{C.END}: Rename the current NOTEBOOK session.")
    print(f"  {C.OK}/datasets{C.END}      : List all recorded datasets in this notebook (detailed).")
    print(f"  {C.OK}/confirm [on|off]{C.END}: Toggle human confirmation before hardware execution.")
    print(f"  {C.OK}/clear{C.END}         : Clear the AI's short-term context.")
    print(f"  {C.OK}/quit{C.END}          : Exit the application and save session.")

def main():
    global active_data_query_session_id # Declare global to modify it

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
    notebook = DigitalLabNotebook(db_path=".talos/lab_notebook.db")
    session_id = notebook.start_experiment(
        title=world_model.get('experiment_name', "Untitled Experiment"),
        context_json=world_model
    )
    active_data_query_session_id = session_id # Initialize with the current notebook session ID

    # 3. Hardware Setup (Decoupled)
    manager, device_ports = connect_devices()
    
    # 4. Capabilities Discovery (Dynamic)
    full_caps = get_instructions(manager, device_ports)
    ai_commands = {}
    ai_guidance = {}
    
    if full_caps:
        for dev, payload in full_caps.items():
            ai_commands[dev] = {k: v for k, v in payload.get('data', {}).items() if v.get('ai_enabled', False)}
            ai_guidance[dev] = payload.get('metadata', {}).get('ai_guidance', "")
    else:
        print(f"{C.WARN}No instrument capabilities discovered. AI will run in simulation mode.{C.END}")

    # Initialize state managers
    plate_manager = PlateManager(max_volume_ul=world_model.get('max_well_volume_ul', 250))
    planner = Planner(world_model, ai_commands, ai_guidance)
    
    # 5. Agent Initialization
    print(f"{C.INFO}[+] Initializing AI Agents (Dual Contexts)...{C.END}")
    
    planner.set_mode(Planner.MODE_RUN)
    run_agent = LLMManager.get_agent(provider=args.provider, model=args.model, context=planner.build_system_context())
    
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
        notebook=notebook,
        require_confirmation=True 
    )

    print(f"\n{C.INFO}System Online. Current Notebook Session: {notebook.current_session_id}, Active Data Query Session: {active_data_query_session_id}{C.END}")
    print(f"{C.INFO}Type /help for a list of commands.{C.END}")

    # 6. REPL Loop
    try:
        while True:
            try:
                mode_str = "RUN" if planner.current_mode == Planner.MODE_RUN else "DATA"
                prompt_color = C.WARN if mode_str == "RUN" else C.OK
                safety_char = "🔒" if executor.require_confirmation else "⚡"
                
                # Dynamic prompt to show current notebook session and active data query session
                current_notebook_info = f"S:{notebook.current_session_id}"
                active_data_info = f"DATA-S:{active_data_query_session_id}" if planner.current_mode == Planner.MODE_DATA else ""
                
                prompt_prefix = f"[{mode_str} {current_notebook_info}"
                if active_data_info:
                    prompt_prefix += f" {active_data_info}"
                prompt_prefix += f" {safety_char}] > "

                user_input = input(f"\n{prompt_color}{prompt_prefix}{C.END}").strip()
                if not user_input: continue
                
                # Assume not a data query from a slash command initially
                query_all_sessions = False # Reset for each loop iteration
                # Store the actual query text from user_input, potentially modified by slash commands
                actual_query_text = user_input 

                # --- Slash Commands ---
                if user_input.startswith("/"):
                    # Use maxsplit=2 to separate command, subcommand, and the rest of the arguments
                    parts = user_input.split(maxsplit=2)
                    cmd = parts[0].lower()
                    subcommand = parts[1].lower() if len(parts) > 1 else None
                    remainder = parts[2] if len(parts) > 2 else ""
                    
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
                        print(f"\n{C.INFO}--- Lab Notebook: All Experiment Sessions ---{C.END}")
                        all_sessions = notebook.get_all_sessions_metadata()
                        if not all_sessions:
                            print("No sessions found in the Digital Lab Notebook.")
                        else:
                            for session_meta in all_sessions:
                                current_marker = " (CURRENT NOTEBOOK SESSION)" if session_meta['id'] == notebook.current_session_id else ""
                                active_data_marker = " (ACTIVE DATA QUERY SESSION)" if session_meta['id'] == active_data_query_session_id else ""
                                print(f"  ID: {C.OK}{session_meta['id']}{C.END} | Title: {session_meta['title']} | Status: {session_meta['status']} | Start: {session_meta['start_time']}{current_marker}{active_data_marker}")
                        continue

                    elif cmd == "/session":
                        if subcommand == "set":
                            try:
                                target_id = int(remainder)
                                all_session_ids = [s['id'] for s in notebook.get_all_sessions_metadata()]
                                if target_id in all_session_ids:
                                    active_data_query_session_id = target_id
                                    data_agent.clear_history() # Clear data agent's history as its context has changed
                                    print(f"{C.INFO}Active data query session switched to ID: {target_id}. Data agent context cleared.{C.END}")
                                else:
                                    print(f"{C.ERR}Session ID {target_id} not found.{C.END}")
                            except ValueError:
                                print(f"{C.ERR}Invalid session ID. Please provide an integer.{C.END}")
                        elif subcommand == "rename":
                            if not remainder:
                                print(f"{C.ERR}Please provide a new title for the current notebook session.{C.END}")
                            else:
                                try:
                                    # This command renames the *current* notebook session, not necessarily the active_data_query_session_id
                                    notebook.update_session_title(notebook.current_session_id, remainder)
                                    print(f"{C.INFO}Current notebook session (ID: {notebook.current_session_id}) renamed to '{remainder}'.{C.END}")
                                except ExperimentFinalizedError as e:
                                    print(f"{C.ERR}{e}{C.END}")
                                except ValueError as e:
                                    print(f"{C.ERR}{e}{C.END}")
                        else: # Just /session (no subcommand)
                            print(f"{C.INFO}Current Notebook Session ID: {notebook.current_session_id}{C.END}")
                            print(f"{C.INFO}Active Data Query Session ID: {active_data_query_session_id}{C.END}")
                            print(f"\n{C.INFO}--- All Available Sessions ---{C.END}")
                            all_sessions = notebook.get_all_sessions_metadata()
                            if not all_sessions:
                                print("No sessions found.")
                            else:
                                for session_meta in all_sessions:
                                    current_marker = " (CURRENT NOTEBOOK)" if session_meta['id'] == notebook.current_session_id else ""
                                    active_data_marker = " (ACTIVE DATA QUERY)" if session_meta['id'] == active_data_query_session_id else ""
                                    print(f"  ID: {C.OK}{session_meta['id']}{C.END} | Title: {session_meta['title']} | Status: {session_meta['status']}{current_marker}{active_data_marker}")
                        continue # Always continue loop after /session commands

                    elif cmd == "/run":
                        planner.set_mode(Planner.MODE_RUN)
                        current_agent = run_agent
                        print(f"{C.INFO}Switched to RUN (Controller).{C.END}")
                        if remainder:
                            actual_query_text = remainder # Treat remainder as the goal for execution
                            # FALL THROUGH to general processing logic
                        else:
                            continue # Just switched mode, no immediate goal, continue loop

                    elif cmd == "/data":
                        planner.set_mode(Planner.MODE_DATA)
                        current_agent = data_agent
                        print(f"{C.INFO}Switched to DATA (Analyst).{C.END}")
                        
                        if subcommand == "all":
                            query_all_sessions = True
                            if remainder:
                                actual_query_text = remainder # Query is after "/data all"
                                # FALL THROUGH to general processing logic
                            else:
                                continue # Just "/data all", no query, continue loop
                        elif subcommand: # e.g., /data what happened
                            actual_query_text = f"{subcommand} {remainder}".strip() # Query is after "/data"
                            # FALL THROUGH to general processing logic
                        else: # Just "/data", no query provided
                            continue # Just switched mode, no immediate query, continue loop

                    else: # Unknown slash command
                        print(f"{C.ERR}Unknown command: {cmd}{C.END}")
                        continue # Continue loop after unknown slash command

                # --- Main Processing Logic for user input (either from non-slash input or a /run /data command with a goal/query) ---
                executor.agent = current_agent # Ensure executor uses the correct agent
                
                # Only process if actual_query_text is not empty
                if actual_query_text:
                    if planner.current_mode == Planner.MODE_RUN:
                        executor.run(actual_query_text)

                    elif planner.current_mode == Planner.MODE_DATA:
                        # This block now handles both direct queries and queries from /data commands
                        print(f"[*] Querying Digital Lab Notebook records...")
                        injected_context = ""

                        # Ensure the reflective log for the *current notebook session* is up-to-date
                        # This covers the case where the current session is also the active data query session.
                        notebook.update_reflective_log(notebook.current_session_id)
                        
                        # 1. Semantic search for high-level summaries
                        if query_all_sessions: # This flag is set by /data all
                            mem_results = notebook.query_vector_all_sessions(actual_query_text, n_results=5)
                            injected_context += "\n=== HISTORICAL SUMMARIES (Semantic Search - ALL SESSIONS) ===\n"
                        else:
                            # Use active_data_query_session_id for the query
                            mem_results = notebook.query_vector(actual_query_text, session_id=active_data_query_session_id, n_results=3)
                            injected_context += f"\n=== HISTORICAL SUMMARIES (Semantic Search - Session {active_data_query_session_id}) ===\n"

                        if not mem_results:
                            injected_context += "No relevant historical summaries found.\n"
                        else:
                            for res in mem_results:
                                # Extract relevant info from ScienceLog.data for the prompt
                                summary_data = res.data.get('summary') or res.data.get('goal') or res.data.get('notes') or str(res.data)
                                injected_context += f"- [Session {res.session_id}, Log {res.id}, Type: {res.entry_type}]: {summary_data[:150]}...\n"

                        # 2. Coordinate scanning (e.g., G9) - This part remains a placeholder for deeper integration
                        coords = re.findall(r"\b([A-H](?:1[0-2]|[1-9]))\b", actual_query_text.upper())
                        if coords:
                            injected_context += f"\n=== COORDINATE SCANNING (Wells found in query: {', '.join(coords)}) ===\n"
                            injected_context += f"  (Context for these wells would be retrieved from ScienceLog.data if available in the active data session)\n"

                        final_prompt = f"{injected_context}\n\nUSER QUESTION: {actual_query_text}"
                        print(f"[*] Analyzing...")
                        response = current_agent.prompt(final_prompt, use_history=True)
                        print(f"\n{C.OK}{response}{C.END}")
                        
                # End of current input processing. Loop will continue for next prompt.

            except KeyboardInterrupt:
                print(f"\n{C.WARN}Interrupted.{C.END}")
                continue

    finally:
        print(f"\n{C.INFO}Shutting down...")
        # Ensure the final_summary is not empty or None for finalize
        summary_text = "User exited Cockpit."
        if notebook.current_session_id is not None:
            # Attempt to get a summary from the LLM based on session's science logs
            try:
                # Update reflective log one last time for the current session
                notebook.update_reflective_log(notebook.current_session_id)
                # Query the current session's reflective log for a summary
                session_summary_logs = notebook.query_vector(
                    "summarize this experiment session", 
                    session_id=notebook.current_session_id, 
                    n_results=1
                )
                if session_summary_logs:
                    # Look for an existing 'summary' entry or pick the most relevant one
                    found_summary = None
                    for log_entry in session_summary_logs:
                        if log_entry.entry_type == 'summary' and log_entry.data.get('text'):
                            found_summary = log_entry.data['text']
                            break
                    if not found_summary and session_summary_logs[0].data:
                        found_summary = session_summary_logs[0].data.get('summary') or session_summary_logs[0].data.get('reflection') or session_summary_logs[0].data.get('text') or str(session_summary_logs[0].data)
                    if found_summary:
                        summary_text = f"AI-generated summary: {found_summary[:200]}..." # Limit for brevity
            except Exception as e:
                print(f"{C.WARN}Could not auto-generate final summary: {e}{C.END}")
                # Fallback to default if AI summary fails
        
        notebook.finalize(summary_text=summary_text) 
        manager.stop()
        print(f"{C.OK}Goodbye.{C.END}")

if __name__ == "__main__":
    main()