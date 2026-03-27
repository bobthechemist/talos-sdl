import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from host.dln.storage_manager import StorageManager

def test_phase1():
    print("[*] Initializing StorageManager...")
    sm = StorageManager(base_dir=".talos_test")
    
    print("[*] Creating test experiment...")
    world_config = {"pump_1": "HCl", "temp_limit": 50}
    exp_id = sm.create_experiment(
        title="Titration Test", 
        objective="Verify StorageManager works", 
        world_model=world_config
    )
    print(f"    Created Exp UUID: {exp_id}")
    
    print("[*] Logging an entry...")
    entry_id = sm.log_entry(exp_id, "user_prompt", {"text": "Add 10ml of HCl"})
    
    print("[*] Saving a dummy data artifact (Registry replacement)...")
    dummy_payload = {
        "metadata": {"data_type": "spectrum", "units": "counts"},
        "data": {"415nm": 100, "445nm": 150, "480nm": 200}
    }
    artifact_id = sm.save_artifact(exp_id, entry_id, "colorimeter", "measure", dummy_payload)
    print(f"    Saved Artifact ID: {artifact_id}")
    
    print("[*] Completing experiment...")
    sm.update_experiment(exp_id, status="completed", summary="Test successful.")
    
    print("\n[SUCCESS] Phase 1 verification complete.")
    print(f"Check the '.talos_test' directory for 'lab_notebook.db' and files in 'data_storage/{exp_id}/'")

if __name__ == "__main__":
    test_phase1()