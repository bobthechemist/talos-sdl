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
        """Answers questions about experimental data using a multi-step RAG strategy."""
        query = " ".join(args)
        if not query:
            print(f"{C.ERR}Usage: /data <your question here>{C.END}")
            return
            
        print("[*] Querying Digital Lab Notebook records...")
        
        # --- The New RAG Strategy ---
        # 1. Entity Extraction (simplified with regex for now)
        entities = self._extract_entities(query)
        print(f"  -> Identified entities: {entities}")

        # 2. Semantic Search (for high-level context)
        context_logs = self.dln.query_vector(query, session_id=self.app.active_data_session_id, n_results=5)

        # 3. Relational Search (for raw, factual data based on entities)
        fact_logs = []
        if entities.get('wells'):
            for well in entities['wells']:
                # This is a simplified query; a real one might be more complex
                sql = f"SELECT * FROM ScienceLog WHERE session_id = {self.app.active_data_session_id} AND json_extract(data, '$.context_tags.well') = '{well}' AND entry_type = 'observation' ORDER BY timestamp DESC LIMIT 5"
                results = self.dln.query_relational(sql)
                fact_logs.extend(results)

        # 4. Synthesize and Prompt
        injected_context = self._synthesize_context(context_logs, fact_logs)
        final_prompt = f"{injected_context}\n\nUSER QUESTION: {query}"
        
        print("[*] Analyzing...")
        response = self.app.ai_agent.prompt(final_prompt, use_history=True)
        print(f"\n{C.OK}{response}{C.END}")

    def _extract_entities(self, query: str) -> dict:
        """Extracts key experimental entities from a query. (Simple version)"""
        # A more advanced version would use an LLM call for robust extraction.
        wells = re.findall(r"\b([A-H](?:1[0-2]|[1-9]))\b", query.upper())
        return {"wells": list(set(wells))} # Return unique wells

    def _synthesize_context(self, context_logs, fact_logs_raw):
            """Combines semantic context and factual observations for the LLM."""
            context = "--- CONTEXT: EXPERIMENT HISTORY (LOGS) ---\n"
            
            for log in context_logs:
                # Check if this log is an envelope (Plan type)
                if log.entry_type == 'plan':
                    intent = log.data.get('intent', 'N/A')
                    edits = log.data.get('human_edits', [])
                    edit_summary = "; ".join([f"Step {e['action']} at {e['step']}: {e['rationale']}" for e in edits])
                    context += f"[Plan] Intent: '{intent}'. Human Modifications: {edit_summary}\n"
                else:
                    context += f"[{log.entry_type.upper()}]: {str(log.data)[:200]}...\n"

            context += "\n--- CONTEXT: RAW DATA LOGS (FACTUAL) ---\n"
            if not fact_logs_raw:
                context += "No specific raw observation data found for these wells.\n"
            else:
                for row in fact_logs_raw:
                    # row[4] is the 'data' field from the science log
                    log_data = json.loads(row[4]) 
                    context += f"[Observation]: {json.dumps(log_data, indent=2)}\n"
            
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