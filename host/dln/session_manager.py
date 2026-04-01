# host/dln/session_manager.py
from host.dln.storage_manager import StorageManager
from host.dln.memory_manager import MemoryManager
from datetime import datetime

class SessionManager:
    def __init__(self, base_dir=".talos"):
        self.storage = StorageManager(base_dir=base_dir)
        self.memory = MemoryManager(base_dir=base_dir)
        self.current_exp_id = None

    def start_session(self, world_model, title=None, objective=None):
        self.current_exp_id = self.storage.create_experiment(
            title=title, objective=objective, world_model=world_model
        )
        return self.current_exp_id

    def log_intent(self, goal):
        return self.storage.log_event(self.current_exp_id, "INTENT", {"goal": goal})

    def log_plan(self, plan):
        return self.storage.log_event(self.current_exp_id, "PLAN", {"plan": plan})

    def save_observation(self, entry_id, device, command, payload, tags=None):
        return self.storage.save_artifact(
            self.current_exp_id, entry_id, device, command, payload, tags=tags
        )

    def log_reflection(self, summary, index_semantically=True):
        entry_id = self.storage.log_event(self.current_exp_id, "REFLECTION", {"summary": summary})
        if index_semantically:
            self.memory.index_experiment(
                exp_id=f"{self.current_exp_id}_{entry_id}",
                text_content=summary,
                metadata={"experiment_id": self.current_exp_id}
            )
        return entry_id

    def search_memory(self, query, n_results=3):
        return self.memory.search_semantic(query, n_results=n_results)

    def end_session(self, summary=None):
        """Restored method to close the SQL record."""
        if self.current_exp_id:
            self.storage.update_experiment(
                self.current_exp_id, 
                status="completed", 
                summary=summary
            )