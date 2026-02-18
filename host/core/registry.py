import os
import json
import csv
import time
from datetime import datetime
from pathlib import Path

class Registry:
    def __init__(self, storage_dir="temp/data", registry_file="temp/registry.json"):
        self.storage_dir = Path(storage_dir)
        self.registry_file = Path(registry_file)
        self._ensure_storage()

    def _ensure_storage(self):
        if not self.storage_dir.exists():
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        if not self.registry_file.exists():
            with open(self.registry_file, 'w') as f:
                json.dump([], f)

    def register(self, origin_device, command, payload):
        """
        Saves data payload to disk and updates the registry.
        Returns the ID of the new dataset.
        """
        timestamp = datetime.now()
        dataset_id = f"ds_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        
        # 1. Save Raw JSON
        json_path = self.storage_dir / f"{dataset_id}.json"
        with open(json_path, 'w') as f:
            json.dump(payload, f, indent=2)
        
        files_created = [str(json_path)]

        # 2. Attempt CSV Conversion (Best Effort for Flat Data)
        # We look into payload['data'] if it exists, otherwise the payload itself
        data_content = payload.get('data', payload)
        
        csv_path = None
        if isinstance(data_content, dict):
            # Check if it's a flat dictionary (values are scalars)
            is_flat = all(isinstance(v, (int, float, str, bool)) for v in data_content.values())
            if is_flat:
                csv_path = self.storage_dir / f"{dataset_id}.csv"
                try:
                    with open(csv_path, 'w', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=data_content.keys())
                        writer.writeheader()
                        writer.writerow(data_content)
                    files_created.append(str(csv_path))
                except Exception as e:
                    print(f"Registry Warning: Could not create CSV for {dataset_id}: {e}")

        # 3. Update Registry Index
        entry = {
            "id": dataset_id,
            "timestamp": timestamp.isoformat(),
            "origin_device": origin_device,
            "origin_command": command,
            "files": files_created,
            "preview": str(data_content)[:100] # Snippet for quick listing
        }

        self._append_to_index(entry)
        return dataset_id, entry

    def _append_to_index(self, entry):
        try:
            with open(self.registry_file, 'r+') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = []
                data.append(entry)
                f.seek(0)
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Registry Error: Failed to update index: {e}")

    def list_datasets(self):
        if not self.registry_file.exists():
            return []
        with open(self.registry_file, 'r') as f:
            return json.load(f)