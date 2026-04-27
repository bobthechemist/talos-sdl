# host/cogs/export_cog.py

import csv
import json
import os
from host.cogs.base_cog import BaseCog
from host.gui.console import C


class ExportCog(BaseCog):
    """Exports experiment data as CSV files."""

    def get_commands(self):
        return {
            "/export": self.handle_export,
        }

    def _flatten(self, data, prefix=""):
        """Flatten a nested dict into dot-notation keys."""
        items = {}
        if not isinstance(data, dict):
            return {prefix: data} if prefix else {}
        for key, value in data.items():
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                items.update(self._flatten(value, new_key))
            else:
                items[new_key] = value
        return items

    def _extract_position(self, payload):
        """Extract x, y, z, angle from a payload if present."""
        pos = payload.get("position")
        if isinstance(pos, dict):
            return {
                "x": pos.get("x"),
                "y": pos.get("y"),
                "z": pos.get("z"),
                "a": pos.get("angle"),
            }
        return None

    def handle_export(self, *args):
        session_id = self.app.active_data_session_id
        export_dir = os.path.join(os.path.dirname(self.dln.db_path), "exports")
        os.makedirs(export_dir, exist_ok=True)

        # ── 1. Export ScienceLog ──────────────────────────────────────────
        science_rows = self.dln.query_relational(
            f"SELECT id, session_id, timestamp, entry_type, data "
            f"FROM ScienceLog WHERE session_id = {session_id} ORDER BY timestamp ASC"
        )

        science_csv = os.path.join(export_dir, f"session_{session_id}_science.csv")
        with open(science_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "session_id", "timestamp", "entry_type", "data"])
            for row in science_rows:
                log_id, sid, ts, entry_type, data_str = row
                data_json = json.dumps(json.loads(data_str))
                writer.writerow([log_id, sid, ts, entry_type, data_json])

        # ── 2. Export TransactionLog ──────────────────────────────────────
        txn_rows = self.dln.query_relational(
            f"SELECT id, session_id, timestamp, raw_io "
            f"FROM TransactionLog WHERE session_id = {session_id} ORDER BY timestamp ASC"
        )

        txn_csv = os.path.join(export_dir, f"session_{session_id}_transactions.csv")
        with open(txn_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "session_id", "timestamp", "raw_io"])
            for row in txn_rows:
                writer.writerow(row)

        # ── 3. Export Session metadata ────────────────────────────────────
        session_rows = self.dln.query_relational(
            f"SELECT id, title, start_time, end_time, context_json, "
            f"final_summary, final_hash, status "
            f"FROM ExperimentSession WHERE id = {session_id}"
        )

        session_csv = os.path.join(export_dir, f"session_{session_id}_metadata.csv")
        with open(session_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "title", "start_time", "end_time", "context_json",
                             "final_summary", "final_hash", "status"])
            for row in session_rows:
                writer.writerow(row)

        # ── 4. Export combined sensor + position data ─────────────────────
        self._export_sensor_data(export_dir, session_id)

        print(f"{C.OK}[+] Exported session {session_id} to:{C.END}")
        print(f"    {science_csv}")
        print(f"    {txn_csv}")
        print(f"    {session_csv}")

    def _export_sensor_data(self, export_dir, session_id):
        """
        Export sensor readings with position data.

        Each observation is examined:
        - Position data (x, y, z, a) is tracked per-device and updated
          whenever a payload contains position info.
        - A row is written only when a sensor endpoint reports data.
          Position-only updates do not produce rows on their own.
        - Each sensor endpoint gets its own column (prefixed with device name
          when multiple devices are present).
        """
        science_rows = self.dln.query_relational(
            f"SELECT id, session_id, timestamp, entry_type, data "
            f"FROM ScienceLog WHERE session_id = {session_id} AND entry_type = 'observation' "
            f"ORDER BY timestamp ASC"
        )

        # Track latest position per device
        device_positions = {}
        # Collect all sensor column names
        sensor_columns = set()
        rows = []

        for row in science_rows:
            log_id, sid, ts, entry_type, data_str = row
            data = json.loads(data_str)

            device = data.get("device", "unknown")
            payload = data.get("payload", {})

            # Flatten sensor data (skip position - handled separately)
            flat = self._flatten(payload)
            # Remove position keys from sensor columns
            for key in list(flat.keys()):
                if key.startswith("position."):
                    del flat[key]

            # Check if this observation has sensor data (non-position fields)
            has_sensor_data = len(flat) > 0

            # Extract and update position
            pos = self._extract_position(payload)
            if pos is not None:
                device_positions[device] = pos

            # Only create a row if there's sensor data
            if not has_sensor_data:
                continue

            # Build row: timestamp + latest positions + sensor values
            row_data = {"timestamp": ts}
            for dev, p in device_positions.items():
                prefix = "" if len(device_positions) == 1 else f"{dev}."
                row_data[f"{prefix}x"] = p.get("x")
                row_data[f"{prefix}y"] = p.get("y")
                row_data[f"{prefix}z"] = p.get("z")
                row_data[f"{prefix}a"] = p.get("a")

            row_data.update(flat)
            rows.append(row_data)

            # Track sensor columns
            sensor_columns.update(flat.keys())

        if not rows:
            return

        # Build column order: timestamp, positions, sensor columns (sorted)
        columns = ["timestamp"]
        single_device = len(device_positions) == 1
        if device_positions:
            for dev in device_positions:
                pfx = "" if single_device else f"{dev}."
                columns.extend([f"{pfx}x", f"{pfx}y", f"{pfx}z", f"{pfx}a"])
        columns.extend(sorted(sensor_columns))

        csv_path = os.path.join(export_dir, f"session_{session_id}_data.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
