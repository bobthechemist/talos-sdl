# host/dln/session_manager.py
from host.dln.storage_manager import StorageManager
from datetime import datetime

# host/dln/session_manager.py
# [Keep existing imports...]

class SessionManager:
    def __init__(self, base_dir=".talos"):
        self.storage = StorageManager(base_dir=base_dir)
        self.current_exp_id = None

    # [Keep existing session/event/data methods...]

    def start_session(self, world_model, title=None, objective=None):
        if not title: title = f"Experiment {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        self.current_exp_id = self.storage.create_experiment(title=title, objective=objective, world_model=world_model)
        return self.current_exp_id

    def log_event(self, entry_type, content):
        if not self.current_exp_id: return None
        return self.storage.log_entry(self.current_exp_id, entry_type, content)

    def save_data(self, entry_id, device, command, payload):
        if not self.current_exp_id: return None
        return self.storage.save_artifact(self.current_exp_id, entry_id, device, command, payload)

    def end_session(self, summary=None, status="completed"):
        if not self.current_exp_id: return
        self.storage.update_experiment(self.current_exp_id, status=status, summary=summary)

    # --- NEW PROTOCOL PROXIES ---

    def save_protocol(self, name, description, plan):
        return self.storage.save_protocol(name, description, plan)

    def load_protocol(self, name):
        return self.storage.load_protocol(name)

    def list_protocols(self):
        return self.storage.list_protocols()