import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# --- Path Setup to include 'host' package ---
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

from host.ai.llm_manager import LLMManager 
from dln import DigitalLabNotebook, verification # New DLN imports
from host.gui.console import C

# Load environment variables (API Keys)
load_dotenv()

def load_file(filepath):
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except FileNotFoundError:
        print(f"{C.ERR}Error: File not found '{filepath}'{C.END}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Generate a Lab Report from Digital Lab Notebook (DLN) records.")
    
    # Arguments
    parser.add_argument("experiment_id", type=int, help="The ID of the experiment session to summarize.")
    parser.add_argument("--output", required=True, help="Filename for the output Markdown report.")
    parser.add_argument("--template", required=True, help="Path to the Markdown template file.")
    parser.add_argument("--agent", default="gemini", help="AI Provider (default: gemini).")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Model name (default: gemini-2.5-flash-lite).")

    args = parser.parse_args()

    # 1. Validation
    # No log file check, we rely on DB existence

    # 2. User Context Input
    print(f"\n{C.INFO}--- Experiment Context ---{C.END}")
    print("Please provide specific experimental details to aid the summary.")
    print("(e.g., 'This was a titration of Acetic Acid with NaOH using Universal Indicator')")
    user_context = input(f"{C.WARN}> {C.END}").strip()
    if not user_context:
        print(f"{C.WARN}No context provided. Proceeding with log data only.{C.END}")
        user_context = "No specific user context provided."

    # 3. Load Data from New DLN
    print(f"{C.INFO}Loading log data and template...{C.END}")
    template_content = load_file(args.template)

    # Initialize the new DLN (assuming it's in .talos)
    notebook = DigitalLabNotebook(db_path=".talos/lab_notebook.db") 
    
    # Retrieve ExperimentSession data
    exp_session_raw = notebook.query_relational(f"SELECT id, title, start_time, end_time, context_json, final_summary, final_hash, status FROM ExperimentSession WHERE id = {args.experiment_id}")
    if not exp_session_raw:
        print(f"{C.ERR}Error: Experiment session with ID {args.experiment_id} not found.{C.END}")
        sys.exit(1)
    
    # Convert raw tuple result to dictionary for easier access
    session_data = dict(zip(['id', 'title', 'start_time', 'end_time', 'context_json', 'final_summary', 'final_hash', 'status'], exp_session_raw[0]))
    session_start_time = session_data['start_time'].isoformat() if session_data['start_time'] else datetime.now().isoformat()
    
    # Ensure context_json is parsed correctly for safe access
    session_context = json.loads(session_data.get('context_json', '{}')) if isinstance(session_data.get('context_json'), str) else session_data.get('context_json', {})


    # Retrieve ScienceLog entries
    science_logs_raw = notebook.query_relational(f"SELECT id, timestamp, entry_type, data, supersedes_id, correction_reason FROM ScienceLog WHERE session_id = {args.experiment_id} ORDER BY timestamp ASC")
    
    # Retrieve TransactionLog entries
    transaction_logs_raw = notebook.query_relational(f"SELECT id, timestamp, raw_io FROM TransactionLog WHERE session_id = {args.experiment_id} ORDER BY timestamp ASC")

    # Format logs into a structured list of dicts for the LLM prompt
    formatted_science_logs = []
    for log_id, timestamp, entry_type, data_json, supersedes_id, correction_reason in science_logs_raw:
        formatted_science_logs.append({
            "log_id": log_id, "timestamp": timestamp.isoformat(), "type": entry_type,
            "data": json.loads(data_json), "supersedes": supersedes_id, "reason": correction_reason
        })
    
    formatted_transaction_logs = []
    for log_id, timestamp, raw_io in transaction_logs_raw:
        formatted_transaction_logs.append({
            "log_id": log_id, "timestamp": timestamp.isoformat(), "raw_io": raw_io
        })

    # Prepare basic template tokens for direct replacement (e.g., title, date)
    replacements = {
        "{{ EXPERIMENT_TITLE }}": session_data.get('title', 'N/A'),
        "{{ DATE }}": session_start_time.split('T')[0],
        "{{ SESSION_ID }}": str(session_data['id']),
        "{{ OBJECTIVE_SUMMARY }}": session_context.get('objective', 'No objective provided.'), 
        "{{ CONNECTED_DEVICES }}": "See details in log.", # This would need more parsing from logs
        "{{ REAGENTS_LIST }}": json.dumps(session_context.get('reagents', {}), indent=2), # Get from world model
        "{{ PROCEDURAL_SUMMARY }}": "See detailed log below.", # LLM will fill this in detail
        "{{ DATA_ANALYSIS }}": "See detailed log below.", # LLM will fill this in detail
        "{{ SCIENTIFIC_CONCLUSION }}": session_data.get('final_summary', 'No conclusion yet.'),
        "{{ RECOMMENDATIONS }}": "N/A" # LLM can fill this if asked
    }

    # Apply initial replacements to the template content
    for key, value in replacements.items():
        template_content = template_content.replace(key, value)

    # 4. Prepare Prompt for the LLM
    # The LLM will now interpret the structured data from the DLN

    system_instruction = """You are an expert Laboratory Data Scientist. 
Your task is to write a formal electronic laboratory notebook entry based on a robotic execution log.
You will be provided with:
1. A Markdown Template.
2. Structured JSON data from a Digital Lab Notebook (DLN) session (Experiment Session Metadata, Science Logs, and Transaction Logs).
3. User context about the experiment.

**GUIDELINES:**
- **Strictly** follow the structure of the provided template.
- **Extract Data:** Look for 'observation' entries in Science Logs. If spectral or tabular data is present in the 'data' field, format it into clear Markdown tables in the 'Observations & Results' section.
- **Interpret:** Do not just list logs. Interpret the actions and findings (e.g., "created a serial dilution" from plan and intent logs, "measured pH" from observation logs).
- **Scientific Tone:** Use passive voice where appropriate for methods, and active analytical voice for conclusions.
- **Completeness:** Ensure all sections of the template are filled using information from the DLN and user context.
"""

    user_prompt = f"""
--- USER CONTEXT ---
{user_context}

--- MARKDOWN TEMPLATE ---
{template_content}

--- DLN SESSION DATA ---
**Experiment Session Metadata:**
{json.dumps(session_data, indent=2)}

**Science Log Entries:**
{json.dumps(formatted_science_logs, indent=2)}

**Transaction Log Entries (recent 20):**
{json.dumps(formatted_transaction_logs[-20:], indent=2)} # Limit transaction logs for brevity in prompt
"""

    # 5. Initialize Agent
    print(f"{C.INFO}Initializing Agent ({args.agent} / {args.model})...{C.END}")
    try:
        agent = LLMManager.get_agent(
            provider=args.agent, 
            model=args.model, 
            context=system_instruction
        )
    except Exception as e:
        print(f"{C.ERR}Failed to initialize agent: {e}{C.END}")
        sys.exit(1)

    # 6. Generate Summary
    print(f"{C.INFO}Generating report... (This may take a moment){C.END}")
    response = agent.prompt(user_prompt, use_history=False)

    if response:
        # 7. Save Output
        try:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(response)
            print(f"\n{C.OK}Success! Report saved to: {args.output}{C.END}")
        except Exception as e:
            print(f"{C.ERR}Failed to write output file: {e}{C.END}")
    else:
        print(f"{C.ERR}Agent returned no response.{C.END}")

if __name__ == "__main__":
    main()