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
    parser = argparse.ArgumentParser(description="Generate a Lab Report from ALIF Logs.")
    
    # Arguments
    parser.add_argument("log_file", help="Path to the JSON conversation log.")
    parser.add_argument("--output", required=True, help="Filename for the output Markdown report.")
    parser.add_argument("--template", required=True, help="Path to the Markdown template file.")
    parser.add_argument("--agent", default="gemini", help="AI Provider (default: gemini).")
    parser.add_argument("--model", default="gemini-2.5-flash-lite", help="Model name (default: gemini-2.5-flash-lite).")

    args = parser.parse_args()

    # 1. Validation
    if not os.path.exists(args.log_file):
        print(f"{C.ERR}Log file does not exist: {args.log_file}{C.END}")
        sys.exit(1)

    # 2. User Context Input
    print(f"\n{C.INFO}--- Experiment Context ---{C.END}")
    print("Please provide specific experimental details to aid the summary.")
    print("(e.g., 'This was a titration of Acetic Acid with NaOH using Universal Indicator')")
    user_context = input(f"{C.WARN}> {C.END}").strip()

    if not user_context:
        print(f"{C.WARN}No context provided. Proceeding with log data only.{C.END}")
        user_context = "No specific user context provided."

    # 3. Load Data
    print(f"{C.INFO}Loading log data and template...{C.END}")
    raw_log = load_file(args.log_file)
    template_content = load_file(args.template)

    # 4. Prepare Prompt
    # We strip the log to valid JSON if possible, though the raw text usually works for LLMs
    try:
        log_json = json.loads(raw_log)
        # Calculate date from the first timestamp
        session_date = log_json[0].get('timestamp', datetime.now().isoformat())
    except:
        session_date = datetime.now().isoformat()
        log_json = raw_log # Fallback to raw text

    system_instruction = """You are an expert Laboratory Data Scientist. 
Your task is to write a formal electronic laboratory notebook entry based on a robotic execution log.
You will be provided with:
1. A Markdown Template.
2. A raw JSON log of the robotic session.
3. User context about the experiment.

**GUIDELINES:**
- **Strictly** follow the structure of the provided template.
- **Extract Data:** Look for "DATA_RESPONSE" events in the log. If spectral data exists, format it into clear Markdown tables in the 'Results' section.
- **Interpret:** Do not just list commands. Interpret the actions (e.g., "created a serial dilution" instead of "moved to C1, dispensed, moved to C2...").
- **Scientific Tone:** Use passive voice where appropriate for methods, and active analytical voice for conclusions.
- **Timestamps:** Use the log timestamps to fill the Date/Session ID.
"""

    user_prompt = f"""
--- USER CONTEXT ---
{user_context}

--- MARKDOWN TEMPLATE ---
{template_content}

--- SESSION LOG (JSON) ---
{json.dumps(log_json, indent=None)}
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