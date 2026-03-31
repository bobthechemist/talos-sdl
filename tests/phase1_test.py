# tests/phase1_test.py
import sys
import os
import shutil
from pathlib import Path

# Setup path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from host.dln.session_manager import SessionManager

def test_generic_ledger():
    test_dir = ".talos_phase1_test"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    print("[*] Initializing SessionManager (Generalized Ledger)...")
    sm = SessionManager(base_dir=test_dir)

    # 1. Start Session with a World Model (Generic)
    world = {
        "description": "General Chemistry Bench",
        "instruments": ["potentiostat_v1", "pump_a"],
        "reagents": {"pump_a": "Ferricyanide Solution"}
    }
    exp_id = sm.start_session(world_model=world, title="Redox Test", objective="Analyze Blue Dye")
    print(f"[+] Session Started: {exp_id}")

    # 2. Log Intent (Audit Trail)
    intent_id = sm.log_intent("Measure the peak current of the blue solution.")
    print(f"[+] Intent Logged: {intent_id}")

    # 3. Log Plan (Audit Trail)
    plan = [
        {"device": "pump_a", "command": "dispense", "args": {"volume": 100}},
        {"device": "potentiostat_v1", "command": "run_cv", "args": {"start_v": 0, "end_v": 0.5}}
    ]
    sm.log_plan(plan)
    print("[+] Plan Logged.")

    # 4. Save Observation with Tags (Hardware-Agnostic Context)
    # Note: These tags are what allows the AI to answer "What was in G9?" 
    # without the database schema knowing what a 'well' is.
    dummy_data = {
        "metadata": {"data_type": "voltammogram"},
        "data": {"voltage": [0.1, 0.2, 0.3], "current": [0.01, 0.05, 0.02]}
    }
    tags = {"sample_id": "blue_dye_01", "well": "G9", "location": "bench_left"}
    obs_id = sm.save_observation(intent_id, "potentiostat_v1", "run_cv", dummy_data, tags=tags)
    print(f"[+] Observation Saved: {obs_id}")

    # 5. Log Reflection (Semantic Memory)
    sm.log_reflection("The blue dye in well G9 showed a clear oxidation peak at 0.22V.")
    print("[+] Reflection Logged and Indexed.")

    # 6. Verify Filesystem
    storage_folder = Path(test_dir) / "data_storage" / exp_id
    files = list(storage_folder.glob("*"))
    print(f"[*] Verified: Found {len(files)} data files in experiment folder.")

    # 7. Test Semantic Recall
    print("[*] Testing Semantic Search for 'blue dye'...")
    results = sm.search_memory("blue dye degradation")
    if results:
        print(f"[SUCCESS] Found record: '{results[0]['content']}'")
    else:
        print("[FAIL] Semantic search returned nothing.")

if __name__ == "__main__":
    test_generic_ledger()