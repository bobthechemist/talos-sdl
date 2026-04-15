# host/cogs/data_cog.py
import json
import re
from host.cogs.base_cog import BaseCog
from host.gui.console import C
from host.ai.prompt_factory import PromptFactory

class DataCog(BaseCog):
    """Manages all data querying, session management, and the RAG workflow."""

    def get_commands(self):
        return {
            "/data": self.handle_data,
            "/session": self.handle_session,
            "/datasets": self.handle_datasets,
        }

    def handle_data(self, *args):
            """Fetches the chronological transcript of the session."""
            query = " ".join(args)
            
            print("[*] Querying Digital Lab Notebook (Transcript)...")
            
            # Fetch ALL logs for this session to reconstruct the transcript
            sql = f"SELECT id, entry_type, data FROM ScienceLog WHERE session_id = {self.app.active_data_session_id} ORDER BY timestamp ASC"
            logs = self.dln.query_relational(sql)

            # Synthesize context chronologically
            injected_context = "--- CHRONOLOGICAL EXPERIMENT TRANSCRIPT ---\n"
            # Truncation: only process the last 15 logs to keep within 32k context
            for log in logs[-15:]:
                log_id, entry_type, data_str = log
                data = json.loads(data_str)
                
                if entry_type == 'plan':
                    intent = data.get('intent', 'N/A')
                    edits = data.get('human_edits', [])
                    edit_summary = "; ".join([f"Step {e.get('step')}: {e.get('rationale')}" for e in edits])
                    injected_context += f"Plan ID {log_id}: '{intent}'. Edits: {edit_summary}\n"
                elif entry_type == 'observation':
                    meta = data.get('plan_metadata', {})
                    injected_context += f"Observation (PlanID: {meta.get('plan_id')}, Step: {meta.get('step_index')}): {json.dumps(data.get('payload'))}\n"
                else:
                    injected_context += f"{entry_type.upper()}: {json.dumps(data)}\n"

            final_prompt = f"{injected_context}\n\nUSER QUESTION: {query}"
            
            print("[*] Analyzing...")
            response = self.app.ai_agent.prompt(final_prompt, use_history=True)
            self.dln.log_science(entry_type="analysis", data={"query": query, "response": response})
            print(f"\n{C.OK}{response}{C.END}")

    def _extract_entities(self, query: str) -> dict:
        """Extracts key experimental entities from a query. (Simple version)"""
        # A more advanced version would use an LLM call for robust extraction.
        wells = re.findall(r"\b([A-H](?:1[0-2]|[1-9]))\b", query.upper())
        return {"wells": list(set(wells))} # Return unique wells

    def _synthesize_context(self, context_logs, fact_logs_raw):
        """Combines semantic context and factual observations for the LLM."""
        context = "--- CONTEXT: EXPERIMENT HISTORY ---\n"
        
        for log in context_logs:
            if log.entry_type == 'plan':
                intent = log.data.get('intent', 'N/A')
                edits = log.data.get('human_edits', [])
                edit_summary = "; ".join([f"Step {e.get('step')}: {e.get('rationale')}" for e in edits])
                context += f"[Plan ID: {log.id}] Intent: '{intent}'. Edits: {edit_summary}\n"
            else:
                context += f"[{log.entry_type.upper()}]: {str(log.data)[:150]}...\n"

        context += "\n--- CONTEXT: RAW DATA LOGS (FACTUAL) ---\n"
        for row in fact_logs_raw:
            log_data = json.loads(row[4]) 
            meta = log_data.get('plan_metadata', {})
            pid = meta.get('plan_id', 'N/A')
            step = meta.get('step_index', 'N/A')
            context += f"[Observation] PlanID: {pid}, Step: {step}, Data: {json.dumps(log_data.get('payload', log_data))}\n"
            
        return context

    def handle_session(self, *args):
        """Manages the active data query session (e.g., /session set 2)."""
        if not args:
            print(f"{C.INFO}Active Data Query Session ID: {self.app.active_data_session_id}{C.END}")
            return
        
        subcommand = args[0].lower()
        if subcommand == "set" and len(args) > 1:
            try:
                target_id = int(args[1])
                # A more robust check would query the DB
                self.app.active_data_session_id = target_id
                self.app.ai_agent.clear_history()
                print(f"{C.OK}Active data query session switched to ID: {target_id}.{C.END}")
            except (ValueError, IndexError):
                print(f"{C.ERR}Usage: /session set <id>{C.END}")
        else:
            print(f"{C.ERR}Unknown session command or missing ID.{C.END}")

    def handle_datasets(self, *args):
        """Lists all recorded experiment sessions in the notebook."""
        print(f"\n{C.INFO}--- Lab Notebook: All Experiment Sessions ---{C.END}")
        all_sessions = self.dln.get_all_sessions_metadata()
        if not all_sessions:
            print("No sessions found in the Digital Lab Notebook.")
            return

        for s in all_sessions:
            active_marker = " (ACTIVE DATA QUERY)" if s['id'] == self.app.active_data_session_id else ""
            print(f"  ID: {C.OK}{s['id']}{C.END} | Title: {s['title']} | Status: {s['status']}{active_marker}")