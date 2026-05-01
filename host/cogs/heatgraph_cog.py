# host/cogs/heatgraph_cog.py
"""
Heatmap Graph Cog for Talos-SDL

Generates spatial heatmaps correlating position data with sensor readings
from the Digital Lab Notebook.
"""

import json
import time
from collections import defaultdict
from host.cogs.base_cog import BaseCog
from host.gui.console import C


class HeatgraphCog(BaseCog):
    """Generates heatmaps from position + sensor observation data."""

    def get_commands(self):
        return {
            "/heatgraph": self.handle_heatgraph,
        }

    def _extract_position(self, payload):
        """Extract x, y, z, angle from a payload if present."""
        # Check top-level first, then nested under "data" key
        pos = payload.get("position")
        if pos is None:
            data = payload.get("data")
            if isinstance(data, dict):
                pos = data.get("position")
        if isinstance(pos, dict):
            return {
                "x": pos.get("x"),
                "y": pos.get("y"),
                "z": pos.get("z"),
                "a": pos.get("angle"),
            }
        return None

    def _resolve_nested_value(self, payload, dotpath):
        """Get a nested value from a payload dict using dot notation (case-insensitive)."""
        # Unwrap "data" key if present (pybot/magnetometer convention)
        data = payload.get("data")
        if isinstance(data, dict):
            payload = data
        parts = dotpath.split(".")
        current = payload
        for part in parts:
            if not isinstance(current, dict):
                return None
            found = False
            for key in current:
                if key.lower() == part.lower():
                    current = current[key]
                    found = True
                    break
            if not found:
                return None
        try:
            return float(current)
        except (ValueError, TypeError):
            return None

    def _extract_sensor_axes(self, payload):
        """
        Flatten nested payload, exclude position keys, find all leaf numeric fields
        that look like measurement axes (e.g., hmc5883.x, tlv493d.y).
        Returns list of axis strings.
        """
        # Unwrap "data" key if present (pybot/magnetometer convention)
        data = payload.get("data")
        if isinstance(data, dict):
            payload = data
        axes = []
        self._flatten_sensor(payload, "", axes, exclude_prefix="position")
        return axes

    def _flatten_sensor(self, data, prefix, axes, exclude_prefix=None):
        """Recursively flatten payload dict, collecting leaf numeric values."""
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if exclude_prefix and key.lower() == exclude_prefix.lower():
                continue
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._flatten_sensor(value, new_key, axes, exclude_prefix)
            elif isinstance(value, (int, float)):
                if prefix:
                    axes.append(new_key)

    def _fetch_observations(self, session_id):
        """Fetch all observation entries from the DLN for the given session."""
        rows = self.dln.query_relational(
            f"SELECT id, session_id, timestamp, entry_type, data "
            f"FROM ScienceLog WHERE session_id = {session_id} AND entry_type = 'observation' "
            f"ORDER BY timestamp ASC"
        )
        observations = []
        for row in rows:
            log_id, sid, ts, entry_type, data_str = row
            data = json.loads(data_str)
            # Convert timestamp to float for comparison
            if isinstance(ts, str):
                try:
                    ts_float = time.mktime(time.strptime(ts[:19], "%Y-%m-%d %H:%M:%S"))
                except (ValueError, TypeError):
                    ts_float = time.time()
            else:
                ts_float = float(ts)
            observations.append({
                "id": log_id,
                "device": data.get("device", "unknown"),
                "command": data.get("command", ""),
                "payload": data.get("payload", {}),
                "timestamp": ts_float,
            })
        return observations

    def _get_position_device_names(self, observations):
        """Find device names that have position data in their payloads."""
        devices = set()
        for obs in observations:
            pos = self._extract_position(obs["payload"])
            if pos is not None and all(v is not None for v in pos.values()):
                devices.add(obs["device"])
        return devices

    def _get_sensor_device_names(self, observations):
        """Find device names that have sensor measurement data in their payloads."""
        devices = set()
        for obs in observations:
            axes = self._extract_sensor_axes(obs["payload"])
            if axes:
                devices.add(obs["device"])
        return devices

    def _correlate_position_to_sensors(self, observations):
        """
        Correlate position data with sensor readings by timestamp.

        For each sensor observation, find the most recent position observation
        from a position device. Returns dict mapping axis_name -> list of data points.
        """
        # Step 1: Separate position observations by device
        position_by_device = defaultdict(list)
        # Step 2: Collect sensor readings
        sensor_readings = []

        for obs in observations:
            device = obs["device"]
            payload = obs["payload"]
            timestamp = obs["timestamp"]

            # Check for position data
            pos = self._extract_position(payload)
            if pos is not None and all(v is not None for v in pos.values()):
                position_by_device[device].append({
                    "x": pos["x"], "y": pos["y"], "z": pos["z"],
                    "a": pos["a"], "timestamp": timestamp,
                })
                continue

            # Check for sensor data
            axes = self._extract_sensor_axes(payload)
            for axis in axes:
                value = self._resolve_nested_value(payload, axis)
                if value is not None:
                    sensor_readings.append({
                        "device": device,
                        "timestamp": timestamp,
                        "axis": axis,
                        "value": value,
                    })

        # Sort position observations by timestamp per device
        for dev in position_by_device:
            position_by_device[dev].sort(key=lambda p: p["timestamp"])

        # For each sensor reading, find the most recent position
        correlated = defaultdict(list)
        for sensor in sensor_readings:
            best_position = None
            best_time = -1.0

            for dev, positions in position_by_device.items():
                for pos in positions:
                    if pos["timestamp"] <= sensor["timestamp"] and pos["timestamp"] > best_time:
                        best_position = pos
                        best_time = pos["timestamp"]

            if best_position is not None:
                correlated[sensor["axis"]].append({
                    "x": best_position["x"],
                    "y": best_position["y"],
                    "z_height": best_position["z"],
                    "value": sensor["value"],
                    "timestamp": sensor["timestamp"],
                })

        return dict(correlated)

    def _group_axes(self, correlated_data):
        """Group sensor axes by their sensor/device prefix name."""
        groups = defaultdict(list)
        skip_prefixes = {"data", "metadata", "position", "payload"}
        for axis in sorted(correlated_data.keys()):
            parts = axis.split(".")
            prefix = parts[0]
            for part in parts:
                if part.lower() not in skip_prefixes:
                    prefix = part
                    break
            groups[prefix].append(axis)
        return dict(groups)

    def handle_heatgraph(self, *args):
        """
        Generate spatial heatmaps correlating position with sensor readings.

        Auto-detects position devices and sensor devices from the session's
        science log. Generates heatmaps for each unique Z height and sensor axis.

        For user invocation: opens matplotlib windows.
        For AI invocation: pass --text-mode as first arg to get text output.
        """
        # Detect mode
        mode = "gui"
        filtered_args = args
        if args and args[0] == "--text-mode":
            mode = "text"
            filtered_args = args[1:]

        session_id = self.app.active_data_session_id
        if session_id is None:
            print(f"{C.ERR}No active session. Start an experiment first.{C.END}")
            if mode == "text":
                return "No active session."
            return

        print("[*] Fetching observation data from lab notebook...")
        observations = self._fetch_observations(session_id)

        if not observations:
            print(f"{C.ERR}No observations found in session {session_id}.{C.END}")
            if mode == "text":
                return "No observations found in session."
            return

        # Auto-detect devices
        position_devices = self._get_position_device_names(observations)
        sensor_devices = self._get_sensor_device_names(observations)

        if not position_devices:
            print(f"{C.ERR}No position devices detected. Cannot generate heatmaps without position data.{C.END}")
            if mode == "text":
                return "No position devices detected. Cannot generate heatmaps without position data."
            return

        if not sensor_devices:
            print(f"{C.ERR}No sensor devices detected. Cannot generate heatmaps without sensor data.{C.END}")
            if mode == "text":
                return "No sensor devices detected. Cannot generate heatmaps without sensor data."
            return

        print(f"{C.OK}Detected position devices: {', '.join(position_devices)}{C.END}")
        print(f"{C.OK}Detected sensor devices: {', '.join(sensor_devices)}{C.END}")

        print("[*] Correlating position data with sensor readings...")
        correlated = self._correlate_position_to_sensors(observations)

        if not correlated:
            print(f"{C.ERR}Could not correlate any position-sensor pairs. Data may be too sparse.{C.END}")
            if mode == "text":
                return "Could not correlate any position-sensor pairs."
            return

        total_points = sum(len(pts) for pts in correlated.values())
        print(f"{C.OK}Correlated {total_points} data points across {len(correlated)} sensor axes.{C.END}")

        sensor_groups = self._group_axes(correlated)

        if mode == "gui":
            return self._generate_gui_heatmaps(correlated, sensor_groups)
        else:
            return self._generate_text_report(correlated, sensor_groups)

    def _generate_gui_heatmaps(self, correlated_data, sensor_groups):
        """Generate and display matplotlib windows for each Z height and sensor axis."""
        import matplotlib
        matplotlib.use("TkAgg")
        import matplotlib.pyplot as plt
        from collections import defaultdict

        num_plots = 0

        for sensor_name in sorted(sensor_groups.keys()):
            axes = sensor_groups[sensor_name]
            for axis in axes:
                data_points = correlated_data[axis]
                if len(data_points) < 3:
                    print(f"{C.WARN}Skipping {axis}: insufficient data ({len(data_points)} points){C.END}")
                    continue

                # Group by Z height
                z_groups = defaultdict(list)
                for dp in data_points:
                    z_key = round(dp["z_height"], 2)
                    z_groups[z_key].append(dp)

                for z_height in sorted(z_groups.keys()):
                    points = z_groups[z_height]
                    x_vals = [p["x"] for p in points]
                    y_vals = [p["y"] for p in points]
                    values = [p["value"] for p in points]

                    fig, ax = plt.subplots(figsize=(8, 6))

                    if len(points) >= 6:
                        contour = ax.tricontourf(x_vals, y_vals, values, levels=20, cmap="viridis")
                        fig.colorbar(contour, ax=ax, label=f"{axis} Value")
                        ax.scatter(x_vals, y_vals, c="white", s=10, alpha=0.5)
                    else:
                        sc = ax.scatter(x_vals, y_vals, c=values, cmap="viridis", s=60, edgecolors="k")
                        fig.colorbar(sc, ax=ax, label=f"{axis} Value")

                    ax.set_title(f"{sensor_name} - {axis} at Z={z_height}")
                    ax.set_xlabel("X (mm)")
                    ax.set_ylabel("Y (mm)")
                    ax.grid(True, alpha=0.3)
                    plt.tight_layout()
                    plt.show()
                    num_plots += 1

        if num_plots == 0:
            print(f"{C.ERR}No valid heatmaps could be generated.{C.END}")
        else:
            print(f"{C.OK}Generated {num_plots} heatmap(s).{C.END}")

    def _generate_text_report(self, correlated_data, sensor_groups):
        """Generate a text description of heatmaps for AI consumption."""
        lines = ["# Heatmap Analysis Report", ""]

        for sensor_name in sorted(sensor_groups.keys()):
            axes = sensor_groups[sensor_name]
            lines.append(f"## Sensor Group: {sensor_name}")
            lines.append("")

            for axis in sorted(axes):
                data_points = correlated_data[axis]
                if len(data_points) < 3:
                    lines.append(f"### {axis}: SKIPPED (insufficient data: {len(data_points)} points)")
                    lines.append("")
                    continue

                z_groups = defaultdict(list)
                for dp in data_points:
                    z_key = round(dp["z_height"], 2)
                    z_groups[z_key].append(dp)

                for z_height in sorted(z_groups.keys()):
                    points = z_groups[z_height]
                    values = [p["value"] for p in points]
                    x_vals = [p["x"] for p in points]
                    y_vals = [p["y"] for p in points]

                    lines.append(f"### {axis} at Z={z_height} ({len(points)} points)")
                    lines.append(f"- X range: {min(x_vals):.2f} to {max(x_vals):.2f}")
                    lines.append(f"- Y range: {min(y_vals):.2f} to {max(y_vals):.2f}")
                    lines.append(f"- Value range: {min(values):.4f} to {max(values):.4f}")
                    lines.append(f"- Mean: {sum(values) / len(values):.4f}")

                    grid = self._describe_grid_heatmap(x_vals, y_vals, values)
                    if grid:
                        lines.append(f"```\n{grid}\n```")
                    lines.append("")

        return "\n".join(lines)

    def _describe_grid_heatmap(self, x_vals, y_vals, values, grid_size=10):
        """Create a simple ASCII grid representation of heatmap data."""
        if not x_vals or not y_vals or not values:
            return ""

        x_min, x_max = min(x_vals), max(x_vals)
        y_min, y_max = min(y_vals), max(y_vals)

        if x_max == x_min:
            x_max = x_min + 1
        if y_max == y_min:
            y_max = y_min + 1

        # Create grid cells
        cell_size_x = (x_max - x_min) / grid_size
        cell_size_y = (y_max - y_min) / grid_size
        grid = [[None for _ in range(grid_size)] for _ in range(grid_size)]
        counts = [[0 for _ in range(grid_size)] for _ in range(grid_size)]

        for x, y, v in zip(x_vals, y_vals, values):
            col = min(int((x - x_min) / cell_size_x), grid_size - 1)
            row = min(int((y - y_min) / cell_size_y), grid_size - 1)
            if 0 <= row < grid_size and 0 <= col < grid_size:
                grid[row][col] = (grid[row][col] or 0) + v
                counts[row][col] += 1

        # Normalize and render
        max_val = max(values) if values else 1
        min_val = min(values) if values else 0
        val_range = max_val - min_val if max_val != min_val else 1

        symbols = " .:-=+*#%@"
        ascii_grid = []
        for row in grid:
            row_str = ""
            for i, cell_val in enumerate(row):
                count = counts[0][i]  # Use first row counts as proxy (simplified)
                if cell_val is not None and count > 0:
                    avg = cell_val / count
                    idx = int(((avg - min_val) / val_range) * (len(symbols) - 1))
                    row_str += symbols[min(idx, len(symbols) - 1)]
                else:
                    row_str += " "
            ascii_grid.append(row_str[::-1])  # Flip horizontal for correct orientation

        return "\n".join(ascii_grid)
